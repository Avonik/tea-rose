"""Deterministic scoring: normalized Qloo data -> *Evidence. No model call, ever.

Definitions follow docs/ARCHITECTURE.md ("Scoring definitions"). Every public function is
TOTAL: missing or empty input yields `None` fields plus a human-readable note, never an
exception.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from tearose.qloo.models import (
    AGE_BUCKETS,
    GENDERS,
    CompareEntity,
    Demographics,
    HeatmapPoint,
    Tag,
)
from tearose.schemas import (
    BridgingEvidence,
    Evidence,
    FameEvidence,
    OverlapEvidence,
    RankedPeer,
    Resolution,
    RoutingDecision,
    ZoneEvidence,
)
from tearose.scoring.raw import DirectionalPeers, RawData

log = logging.getLogger(__name__)

SEARCH_CAP = 150  # 3 pages x take=50: the overlap search depth when not exhausted
MIN_FOUND_STAND_INS = 2  # proxy path: fewer stand-ins found within the depth => censored
TOP_PEERS = 10
TOP_REGIONS = 8
MIN_MAP_POINTS = 5
BROAD_AGE_SPREAD = 0.15  # max-min across age buckets below this => no age skew
BROAD_GENDER_GAP = 0.10  # |male-female| below this => no gender skew
_EPS = 1e-9

# --------------------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------------------


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def percentile_from_rank(rank: float | None, universe_size: int | None) -> float | None:
    """`1 - (rank - 1) / universe_size`, clipped to [0, 1]. None if either input is unusable."""
    if rank is None or universe_size is None or universe_size <= 0 or math.isnan(rank):
        return None
    return _clip01(1.0 - (rank - 1.0) / universe_size)


def mean_rank(ranks: Sequence[float]) -> float | None:
    """Arithmetic mean of ranks; None when empty."""
    return sum(ranks) / len(ranks) if ranks else None


def gini(values: Iterable[float]) -> float | None:
    """Gini coefficient of non-negative values (negatives clipped to 0).

    G = sum_i sum_j |x_i - x_j| / (2 * n^2 * mean), computed as
    sum_i (2i - n - 1) * x_(i) / (n * sum x) over ascending-sorted values (i 1-based).
    0 = perfectly uniform; one non-zero value among n gives (n-1)/n (-> 1 for large n).
    None for empty input or an all-zero vector.
    """
    xs = sorted(max(0.0, float(v)) for v in values)
    n = len(xs)
    if n == 0:
        return None
    total = sum(xs)
    if total <= _EPS:
        return None
    weighted = sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(xs))
    return _clip01(weighted / (n * total))


def cosine(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Cosine similarity of two equal-length vectors; None if lengths differ or a norm is 0."""
    if len(a) != len(b) or not a:
        return None
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= _EPS or nb <= _EPS:
        return None
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


def bin_key(point: HeatmapPoint) -> str:
    """1-decimal lat/lon bin label, e.g. "40.7, -74.0"."""
    return f"{round(point.latitude, 1):.1f}, {round(point.longitude, 1):.1f}"


def bin_points(points: Iterable[HeatmapPoint], use_label: bool = False) -> dict[str, float]:
    """Sum non-negative affinity per bin. Points with affinity None are skipped.

    Bins are 1-decimal lat/lon cells; with `use_label=True` a point's `label` (when present)
    is used as its bin instead. Insertion order follows first appearance.
    """
    bins: dict[str, float] = {}
    for p in points:
        if p.affinity is None:
            continue
        key = p.label.strip() if use_label and p.label and p.label.strip() else bin_key(p)
        bins[key] = bins.get(key, 0.0) + max(0.0, float(p.affinity))
    return bins


def _affinities(points: Iterable[HeatmapPoint]) -> list[float]:
    return [float(p.affinity) for p in points if p.affinity is not None]


def _median(xs: Sequence[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


# --------------------------------------------------------------------------------------
# Overlap
# --------------------------------------------------------------------------------------


def universe_size(peers: DirectionalPeers) -> int:
    """len(entities) if the search was exhausted, else max(len(entities), SEARCH_CAP)."""
    n = len(peers.entities)
    return n if peers.exhausted else max(n, SEARCH_CAP)


def _rank_of(rank: int | None, idx: int) -> int:
    return rank if rank is not None and rank > 0 else idx + 1


def _entity_ranks(peers: DirectionalPeers) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for idx, e in enumerate(peers.entities):
        ranks.setdefault(e.entity_id, _rank_of(e.rank, idx))
    return ranks


def _top_peers(peers: DirectionalPeers | None) -> list[RankedPeer]:
    if peers is None:
        return []
    out = [
        RankedPeer(
            entity_id=e.entity_id, name=e.name, rank=_rank_of(e.rank, idx), affinity=e.affinity
        )
        for idx, e in enumerate(peers.entities)
    ]
    out.sort(key=lambda p: p.rank)
    return out[:TOP_PEERS]


@dataclass
class Direction:
    """One overlap direction: where the target ranks among the seeded category brands
    (censored beyond the scanned depth) plus its directly looked-up affinity."""

    rank: float | None = None  # mean rank over targets; None when censored or not computable
    size: int | None = None  # universe size used for the percentile
    percentile: float | None = None  # rank percentile; None when censored
    censored: bool = False  # a target (or 2+ of 3 stand-ins) lies beyond the list
    depth_scanned: int | None = None  # brands actually returned (pages x take, or fewer)
    target_affinity: float | None = None  # mean over targets with a known affinity
    top1_affinity: float | None = None
    last_scanned_affinity: float | None = None
    affinity_ratio: float | None = None  # target_affinity / top1_affinity, clipped to 0..1
    notes: list[str] = field(default_factory=list)


def _target_affinity(
    peers: DirectionalPeers, targets: list[str], ranks: dict[str, int]
) -> tuple[float | None, int]:
    """Mean affinity over targets: the direct lookup, else the affinity in the scanned list."""
    listed = {e.entity_id: e.affinity for e in peers.entities}
    vals: list[float] = []
    for t in targets:
        a = peers.target_affinities.get(t)
        if a is None and t in ranks:
            a = listed.get(t)
        if a is not None:
            vals.append(float(a))
    return (sum(vals) / len(vals) if vals else None), len(vals)


def direction_stats(
    peers: DirectionalPeers | None, target_ids: Sequence[str], label: str
) -> Direction:
    """Rank of `target_ids` within one seeded peer list, plus the direct affinity signal.

    Rank: with several targets (proxy comparators) the mean of their ranks. A target that is
    not in the scanned list is CENSORED: its rank is only known to lie beyond the depth, so
    rank and percentile are None (harness v1 counted it as rank size + 1, i.e. percentile 0).
    With several stand-ins, at least MIN_FOUND_STAND_INS (2) of them found gives the mean over
    the FOUND ones (noted as "mean over 2 of 3 stand-ins; 1 beyond the 150 strongest"); only
    fewer found censors the direction. The affinity ratio uses all looked-up targets.
    Affinity ratio: mean target affinity (direct lookup, else the listed affinity) divided by
    the affinity of the top-ranked brand of the same seeded list, clipped to 0..1.
    """
    d = Direction()
    if peers is None:
        d.notes.append(f"{label}: no peer list was fetched.")
        return d
    targets = [t for t in dict.fromkeys(target_ids) if t]
    if not targets:
        d.notes.append(f"{label}: no target entity ids to locate.")
        return d
    size = universe_size(peers)
    d.depth_scanned = len(peers.entities)
    if peers.entities:
        d.top1_affinity = peers.entities[0].affinity
        d.last_scanned_affinity = peers.entities[-1].affinity
    ranks = _entity_ranks(peers)
    d.target_affinity, n_aff = _target_affinity(peers, targets, ranks)
    top = d.top1_affinity
    if d.target_affinity is not None and top is not None and top > _EPS:
        d.affinity_ratio = _clip01(d.target_affinity / top)
        looked = f"; {n_aff} of {len(targets)} targets" if len(targets) > 1 else ""
        d.notes.append(
            f"{label}: affinity ratio {d.affinity_ratio:.2f} (target affinity "
            f"{d.target_affinity:.2f} / top-ranked {top:.2f}{looked})."
        )
    elif peers.target_affinities:
        d.notes.append(f"{label}: affinity ratio not computable (no target or top affinity).")
    if size <= 0:
        d.notes.append(f"{label}: the peer universe came back empty.")
        return d
    d.size = size
    missing = [t for t in targets if t not in ranks]
    found = [t for t in targets if t in ranks]
    if missing and len(targets) > 1 and len(found) >= MIN_FOUND_STAND_INS:
        # Partial: the mean over the stand-ins that were found; the rest lie beyond the depth.
        d.rank = mean_rank([float(ranks[t]) for t in found])
        d.percentile = percentile_from_rank(d.rank, size)
        beyond = (
            f"not among the {len(peers.entities)} returned"
            if peers.exhausted
            else f"beyond the {SEARCH_CAP} strongest"
        )
        d.notes.append(
            f"{label}: mean over {len(found)} of {len(targets)} stand-ins; "
            f"{len(missing)} {beyond} (ids: {', '.join(missing)})."
        )
    elif missing:
        d.censored = True
        how = (
            f"not among the {len(peers.entities)} peers returned (complete list)"
            if peers.exhausted
            else f"not found within the first {len(peers.entities)} results "
            f"(search depth {SEARCH_CAP})"
        )
        d.notes.append(
            f"{label}: {len(missing)} of {len(targets)} target(s) {how}; rank censored "
            f"(beyond {len(peers.entities)}), no rank percentile: {', '.join(missing)}."
        )
    else:
        d.rank = mean_rank([float(ranks[t]) for t in targets])
        d.percentile = percentile_from_rank(d.rank, size)
        if len(targets) > 1:
            d.notes.append(f"{label}: rank is the mean over {len(targets)} comparator brands.")
    return d


def _compare_row(e: CompareEntity) -> dict[str, Any]:
    return {
        "entity_id": e.entity_id,
        "name": e.name,
        "a_affinity": e.a_affinity,
        "b_affinity": e.b_affinity,
        "delta": e.delta,
    }


def _fallback_targets(resolution: Resolution | None, side: str) -> list[str]:
    if resolution is None:
        return []
    brand = resolution.senior if side == "senior" else resolution.junior
    proxy = resolution.senior_proxy if side == "senior" else resolution.junior_proxy
    if brand.entity_id:
        return [brand.entity_id]
    if proxy is not None:
        return list(proxy.comparator_brand_ids)
    return []


def _direction_fields(prefix: str, d: Direction) -> dict[str, Any]:
    return {
        f"{prefix}_censored": d.censored,
        f"{prefix}_depth_scanned": d.depth_scanned,
        f"{prefix}_target_affinity": d.target_affinity,
        f"{prefix}_top1_affinity": d.top1_affinity,
        f"{prefix}_last_scanned_affinity": d.last_scanned_affinity,
        f"{prefix}_affinity_ratio": d.affinity_ratio,
    }


def overlap_evidence(raw: RawData, resolution: Resolution | None = None) -> OverlapEvidence:
    """Rank-based shared-purchaser evidence in both directions (see ARCHITECTURE.md).

    Target ids come from `raw.*_target_entity_ids`; if empty, from the resolution (entity id,
    else proxy comparators). `symmetric_percentile` = mean of the available (uncensored) rank
    percentiles; `symmetric_affinity_ratio` = mean of the available affinity ratios.
    Rank fields are the (rounded) mean ranks; percentiles use the unrounded mean.
    """
    notes: list[str] = []
    junior_targets = list(raw.junior_target_entity_ids) or _fallback_targets(resolution, "junior")
    senior_targets = list(raw.senior_target_entity_ids) or _fallback_targets(resolution, "senior")

    s2j = direction_stats(raw.senior_seed_junior_universe, junior_targets, "senior->junior")
    j2s = direction_stats(raw.junior_seed_senior_universe, senior_targets, "junior->senior")
    notes += s2j.notes + j2s.notes

    pcts = [p for p in (s2j.percentile, j2s.percentile) if p is not None]
    symmetric = sum(pcts) / len(pcts) if pcts else None
    if len(pcts) == 1:
        notes.append("Only one direction has a rank percentile; the symmetric one uses it alone.")
    elif not pcts:
        notes.append("No rank percentile in either direction (not computable or censored).")
    for label, pct in (("senior->junior", s2j.percentile), ("junior->senior", j2s.percentile)):
        if pct is not None:
            notes.append(f"{label} percentile: {pct:.2f}.")
    ratios = [r for r in (s2j.affinity_ratio, j2s.affinity_ratio) if r is not None]
    symmetric_ratio = sum(ratios) / len(ratios) if ratios else None

    shared: list[dict[str, Any]] = []
    d_senior: list[dict[str, Any]] = []
    d_junior: list[dict[str, Any]] = []
    if raw.compare is None:
        notes.append("No compare data: shared/distinct affinities are empty.")
    elif raw.compare.insufficient_data:
        notes.append(
            "Compare: insufficient data (no shared tags; typical for a thin brand). "
            "Not evidence of zero overlap."
        )
    elif raw.compare.entities:
        shared = [_compare_row(e) for e in raw.compare.shared()]
        d_senior = [_compare_row(e) for e in raw.compare.distinct_to_a()]
        d_junior = [_compare_row(e) for e in raw.compare.distinct_to_b()]
    else:
        # Documented live shape: /v2/analysis/compare returns tags with query.score that
        # characterize how the two audiences differ. Surface them as "shared affinities".
        shared = [
            {
                "tag_id": t.tag_id,
                "name": t.name,
                "type": t.tag_type,
                "score": t.score if t.score is not None else t.affinity,
            }
            for t in raw.compare.tags[:15]
        ]
        notes.append("Compare returned audience tags (documented shape); no per-entity lists.")

    used_proxy = raw.used_proxy_senior or raw.used_proxy_junior
    if used_proxy:
        flags = (("senior", raw.used_proxy_senior), ("junior", raw.used_proxy_junior))
        sides = [s for s, f in flags if f]
        notes.append(f"Proxy path used for {' and '.join(sides)} (category comparators).")

    return OverlapEvidence(
        senior_to_junior_rank=round(s2j.rank) if s2j.rank is not None else None,
        senior_to_junior_universe=s2j.size,
        senior_to_junior_percentile=s2j.percentile,
        junior_to_senior_rank=round(j2s.rank) if j2s.rank is not None else None,
        junior_to_senior_universe=j2s.size,
        junior_to_senior_percentile=j2s.percentile,
        symmetric_percentile=symmetric,
        **_direction_fields("senior_to_junior", s2j),
        **_direction_fields("junior_to_senior", j2s),
        symmetric_affinity_ratio=symmetric_ratio,
        top_peers_senior_seed=_top_peers(raw.senior_seed_junior_universe),
        top_peers_junior_seed=_top_peers(raw.junior_seed_senior_universe),
        shared_affinities=shared,
        distinct_to_senior=d_senior,
        distinct_to_junior=d_junior,
        used_proxy=used_proxy,
        notes=notes,
    )


# --------------------------------------------------------------------------------------
# Bridging
# --------------------------------------------------------------------------------------


def bridging_evidence(raw: RawData) -> BridgingEvidence:
    """Best (lowest) rank of any junior category tag among the senior's taste tags.

    Universe = len(senior_tags). percentile = 1 - (rank-1)/universe. If no leaf is present,
    the nearest taxonomy ancestor present is used instead (rank reported for the ancestor,
    percentile x 0.5 per level climbed, note "leaf absent; parent <name> at rank k"). Nothing
    present => rank None, percentile 0 and a note. category_affinity = the matched tag's.
    """
    cat_ids = [t for t in dict.fromkeys(raw.junior_category_tag_ids) if t]
    if not cat_ids:
        return BridgingEvidence(
            category_tag_ids=[],
            category_rank_among_senior_tags=None,
            senior_tag_universe=len(raw.senior_tags) or None,
            category_affinity=None,
            percentile=None,
            notes=["No junior category tag ids: bridging not computable."],
        )
    if not raw.senior_tags:
        return BridgingEvidence(
            category_tag_ids=cat_ids,
            category_rank_among_senior_tags=None,
            senior_tag_universe=None,
            category_affinity=None,
            percentile=None,
            notes=["No taste tags returned for the senior seed: bridging not computable."],
        )
    size = len(raw.senior_tags)
    best = _best_tag(raw.senior_tags, set(cat_ids))
    levels = 0
    if best is None:
        # Leaf absent from the senior's top tags (weak evidence with ~177 nodes and take=50):
        # climb the brand taxonomy one level at a time and take the nearest ancestor present.
        frontier = list(cat_ids)
        while best is None:
            frontier = [p for p in (taxonomy_parent(t) for t in frontier) if p]
            if not frontier:
                break
            levels += 1
            best = _best_tag(raw.senior_tags, set(frontier))
    if best is None:
        return BridgingEvidence(
            category_tag_ids=cat_ids,
            category_rank_among_senior_tags=None,
            senior_tag_universe=size,
            category_affinity=None,
            percentile=0.0,
            notes=[
                f"None of the junior's category tags (nor any taxonomy parent) appear among the "
                f"senior's {size} taste tags; percentile set to 0."
            ],
        )
    rank, aff, name, tag_id = best
    notes: list[str] = []
    if size < 50:
        notes.append(f"Small tag universe ({size} tags); percentile is coarse.")
    pct = percentile_from_rank(rank, size)
    if levels:
        pct = pct * ANCESTOR_DISCOUNT**levels if pct is not None else None
        notes.append(
            f"leaf absent; parent {name} at rank {rank}"
            + (f" ({levels} levels up)" if levels > 1 else "")
            + f"; percentile discounted by {ANCESTOR_DISCOUNT} per level climbed."
        )
    else:
        notes.append(f"Best-ranked category tag: {name!r} at rank {rank} of {size}.")
    return BridgingEvidence(
        category_tag_ids=cat_ids,
        category_rank_among_senior_tags=rank,
        senior_tag_universe=size,
        category_affinity=aff,
        percentile=pct,
        matched_tag_id=tag_id,
        matched_tag_name=name,
        ancestor_levels=levels,
        notes=notes,
    )


BRAND_GENRE_ROOT = "urn:tag:genre:brand"
ANCESTOR_DISCOUNT = 0.5  # bridging percentile multiplier per taxonomy level climbed


def taxonomy_parent(tag_id: str) -> str | None:
    """Parent brand-genre tag id (strip the last ':' segment); None at a top family or for
    tags outside `urn:tag:genre:brand` (the bare root is never a meaningful category)."""
    if not tag_id.startswith(BRAND_GENRE_ROOT + ":"):
        return None
    parent = tag_id.rsplit(":", 1)[0]
    return parent if parent.startswith(BRAND_GENRE_ROOT + ":") else None


def _best_tag(tags: Sequence[Tag], wanted: set[str]) -> tuple[int, float | None, str, str] | None:
    """(rank, affinity, name, tag_id) of the best-ranked tag whose id is in `wanted`."""
    best: tuple[int, float | None, str, str] | None = None
    for idx, tag in enumerate(tags):
        if tag.tag_id not in wanted:
            continue
        r = _rank_of(tag.rank, idx)
        if best is None or r < best[0]:
            best = (r, tag.affinity, tag.name, tag.tag_id)
    return best


# --------------------------------------------------------------------------------------
# Fame
# --------------------------------------------------------------------------------------

_AGE_RANGES: dict[str, tuple[int | None, int | None]] = {
    "24_and_younger": (None, 24),
    "25_to_29": (25, 29),
    "30_to_34": (30, 34),
    "35_to_44": (35, 44),
    "45_to_54": (45, 54),
    "55_and_older": (55, None),
}


def _fmt_range(lo: int | None, hi: int | None) -> str:
    if lo is None and hi is None:
        return "all ages"
    if lo is None:
        return f"under {hi + 1}"  # type: ignore[operator]
    if hi is None:
        return f"{lo}+"
    return f"{lo}–{hi}"


def _has_demo(d: Demographics | None) -> bool:
    return d is not None and bool(d.age or d.gender)


def _evenness(values: Sequence[float]) -> float | None:
    """clip(1 - mean(|v|), 0, 1) with v clipped to [-1, 1]; None for an empty vector."""
    if not values:
        return None
    v = [max(-1.0, min(1.0, x)) for x in values]
    return _clip01(1.0 - sum(abs(x) for x in v) / len(v))


def breadth_score(d: Demographics | None) -> float | None:
    """Evenness of appeal across the 8 buckets (6 age + 2 gender), in [0, 1].

    Qloo demographics are relative indices (over/under-indexing against a baseline, about
    -1..1), not shares, so a brand everyone knows sits near 0 everywhere:

        breadth = clip(1 - mean(|v_i|), 0, 1)     v_i clipped to [-1, 1], missing bucket = 0

    Flat zeros => 1.0; mild deviations score high; a strong skew in either direction scores
    low. None only when there is no demographic data at all.
    """
    if d is None or not _has_demo(d):
        return None
    return _evenness(d.age_vector() + d.gender_vector())


def breadth_parts(d: Demographics | None) -> tuple[float | None, float | None]:
    """(age evenness over the 6 age buckets, gender evenness over the 2 genders)."""
    if d is None:
        return None, None
    age = _evenness(d.age_vector()) if d.age else None
    gender = _evenness(d.gender_vector()) if d.gender else None
    return age, gender


def fame_score(
    breadth: float | None, popularity: float | None, coverage: float | None
) -> float | None:
    """Mean of breadth, popularity percentile and heatmap coverage; None unless all three."""
    parts = (breadth, popularity, coverage)
    if any(p is None for p in parts):
        return None
    return sum(parts) / 3.0  # type: ignore[arg-type]


def skew_description(d: Demographics | None) -> str:
    """E.g. "skews 25–34, male"; "broad" when ages are flat (spread < 0.15) and gender gap < 0.1.

    Age part: the two highest age buckets (merged into one range when adjacent, else joined by
    "and"), omitted when ages are flat. Gender part: the gender with the higher affinity,
    omitted when the gap is below 0.1.
    """
    if d is None or not _has_demo(d):
        return "unknown (no demographic data)"
    ages = d.age_vector()
    parts: list[str] = []
    if d.age and max(ages) - min(ages) >= BROAD_AGE_SPREAD:
        # Only buckets that over-index (> 0) count as a skew; the second is dropped when negative.
        positive = (i for i in range(len(AGE_BUCKETS)) if ages[i] > 0)
        top2 = sorted(positive, key=lambda i: (-ages[i], i))[:2]
        if len(top2) == 1:
            parts.append(_fmt_range(*_AGE_RANGES[AGE_BUCKETS[top2[0]]]))
        elif len(top2) == 2:
            i, j = sorted(top2)
            ri, rj = _AGE_RANGES[AGE_BUCKETS[i]], _AGE_RANGES[AGE_BUCKETS[j]]
            if j == i + 1:
                parts.append(_fmt_range(ri[0], rj[1]))
            else:
                parts.append(f"{_fmt_range(*ri)} and {_fmt_range(*rj)}")
    male, female = d.gender_vector()
    if d.gender and abs(male - female) >= BROAD_GENDER_GAP:
        parts.append(GENDERS[0] if male > female else GENDERS[1])
    if not parts:
        return "broad"
    return "skews " + ", ".join(parts)


def heatmap_coverage(points: Sequence[HeatmapPoint]) -> float | None:
    """Share of cells whose affinity is strictly above the response's median; None if < 5."""
    xs = _affinities(points)
    if len(xs) < MIN_MAP_POINTS:
        return None
    med = _median(xs)
    return sum(1 for x in xs if x > med) / len(xs)


def fame_evidence(raw: RawData, resolution: Resolution | None = None) -> FameEvidence:
    """Fame evidence for the SENIOR side (breadth, skew, popularity, national coverage)."""
    notes: list[str] = []
    demo = raw.senior_demographics
    breadth = breadth_score(demo)
    breadth_age, breadth_gender = breadth_parts(demo)
    if not _has_demo(demo):
        notes.append("No demographic data for the senior brand.")

    popularity = raw.senior_popularity
    if popularity is None and resolution is not None and resolution.senior.popularity is not None:
        popularity = resolution.senior.popularity
        notes.append("Popularity taken from entity resolution.")
    if popularity is None:
        notes.append("No popularity percentile for the senior brand.")

    coverage = heatmap_coverage(raw.senior_heatmap_national)
    if coverage is None:
        notes.append(
            f"National heatmap has fewer than {MIN_MAP_POINTS} points with affinity; "
            "coverage not computable."
        )
    return FameEvidence(
        demographics=demo or Demographics(),
        breadth_score=breadth,
        breadth_age=breadth_age,
        breadth_gender=breadth_gender,
        skew_description=skew_description(demo),
        popularity_percentile=popularity,
        heatmap_coverage=coverage,
        fame_score=fame_score(breadth, popularity, coverage),
        notes=notes,
    )


# --------------------------------------------------------------------------------------
# Zone
# --------------------------------------------------------------------------------------


def top_regions(points: Sequence[HeatmapPoint], n: int = TOP_REGIONS) -> list[dict[str, Any]]:
    """Top `n` bins (label when present, else 1-decimal lat/lon) by share of total affinity."""
    bins = bin_points(points, use_label=True)
    total = sum(bins.values())
    if total <= _EPS:
        return []
    ranked = sorted(bins.items(), key=lambda kv: -kv[1])[:n]
    return [{"label": k, "share": v / total} for k, v in ranked]


def geographic_overlap(a: Sequence[HeatmapPoint], b: Sequence[HeatmapPoint]) -> float | None:
    """Cosine similarity over the union of 1-decimal bins; None if either side has < 5 points."""
    if len(_affinities(a)) < MIN_MAP_POINTS or len(_affinities(b)) < MIN_MAP_POINTS:
        return None
    ba, bb = bin_points(a), bin_points(b)
    keys = sorted(set(ba) | set(bb))
    c = cosine([ba.get(k, 0.0) for k in keys], [bb.get(k, 0.0) for k in keys])
    return _clip01(c) if c is not None else None


def zone_evidence(raw: RawData) -> ZoneEvidence:
    """Geographic concentration of the senior's affinity and overlap with the junior's map."""
    notes: list[str] = []
    pts = list(raw.senior_heatmap)
    xs = _affinities(pts)
    concentration: float | None = None
    if len(xs) < MIN_MAP_POINTS:
        notes.append(
            f"Senior heatmap has {len(xs)} point(s) with affinity (< {MIN_MAP_POINTS}); "
            "concentration not computable."
        )
    else:
        concentration = gini(xs)
        if concentration is None:
            notes.append("Senior heatmap affinities are all zero; concentration not computable.")
    regions = top_regions(pts)
    if not regions:
        notes.append("No regions with positive affinity.")
    overlap = geographic_overlap(pts, raw.junior_heatmap)
    if overlap is None:
        notes.append(
            f"Geographic overlap needs at least {MIN_MAP_POINTS} points with affinity on both "
            "sides (and non-zero maps)."
        )
    return ZoneEvidence(
        points=pts,
        concentration_index=concentration,
        top_regions=regions,
        junior_points=list(raw.junior_heatmap),
        geographic_overlap=overlap,
        notes=notes,
    )


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------


def _safe[T](name: str, fn: Callable[[], T], fallback: Callable[[str], T]) -> T:
    """Last-resort guard so one analysis can never crash the run."""
    try:
        return fn()
    except Exception as exc:  # pragma: no cover - defensive; the functions above are total
        log.exception("scoring %s failed", name)
        return fallback(f"{name}: internal scoring error ({type(exc).__name__}: {exc}).")


def compute_evidence(
    raw: RawData | None, resolution: Resolution | None, routing: RoutingDecision | None
) -> Evidence:
    """Run only the analyses in `routing.analyses`; the others stay None. Overlap also stays
    None when the resolve agent judged a stand-in category too far to compare audiences
    (Resolution.overlap_blocked)."""
    data = raw if raw is not None else RawData()
    wanted = set(routing.analyses) if routing is not None else set()
    if resolution is not None and resolution.overlap_blocked():
        wanted.discard("overlap")
    ev = Evidence()
    if "overlap" in wanted:
        ev.overlap = _safe(
            "overlap",
            lambda: overlap_evidence(data, resolution),
            lambda m: OverlapEvidence(
                senior_to_junior_rank=None,
                senior_to_junior_universe=None,
                junior_to_senior_rank=None,
                junior_to_senior_universe=None,
                symmetric_percentile=None,
                notes=[m],
            ),
        )
    if "bridging" in wanted:
        ev.bridging = _safe(
            "bridging",
            lambda: bridging_evidence(data),
            lambda m: BridgingEvidence(
                category_tag_ids=[],
                category_rank_among_senior_tags=None,
                senior_tag_universe=None,
                category_affinity=None,
                percentile=None,
                notes=[m],
            ),
        )
    if "fame" in wanted:
        ev.fame = _safe(
            "fame",
            lambda: fame_evidence(data, resolution),
            lambda m: FameEvidence(
                demographics=Demographics(),
                breadth_score=None,
                skew_description="unknown",
                popularity_percentile=None,
                heatmap_coverage=None,
                notes=[m],
            ),
        )
    if "zone" in wanted:
        ev.zone = _safe(
            "zone",
            lambda: zone_evidence(data),
            lambda m: ZoneEvidence(points=[], concentration_index=None, notes=[m]),
        )
    return ev
