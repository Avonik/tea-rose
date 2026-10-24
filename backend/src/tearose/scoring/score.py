"""Deterministic scoring: normalized Qloo data -> *Evidence. No model call, ever.

Definitions follow docs/ARCHITECTURE.md ("Scoring definitions"). Every public function is
TOTAL: missing or empty input yields `None` fields plus a human-readable note, never an
exception.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from tearose.qloo.models import AGE_BUCKETS, GENDERS, CompareEntity, Demographics, HeatmapPoint
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


def direction_rank(
    peers: DirectionalPeers | None, target_ids: Sequence[str], label: str
) -> tuple[float | None, int | None, float | None, list[str]]:
    """Rank of `target_ids` within one seeded peer list.

    Returns (mean_rank, universe_size, percentile, notes). With several targets (proxy
    comparators) the rank is the mean of their ranks; a target not found counts as
    universe_size + 1 (so percentile 0 when all are missing).
    """
    notes: list[str] = []
    if peers is None:
        return None, None, None, [f"{label}: no peer list was fetched."]
    targets = [t for t in dict.fromkeys(target_ids) if t]
    if not targets:
        return None, None, None, [f"{label}: no target entity ids to locate."]
    size = universe_size(peers)
    if size <= 0:
        return None, None, None, [f"{label}: the peer universe came back empty."]
    ranks = _entity_ranks(peers)
    found: list[float] = []
    missing: list[str] = []
    for t in targets:
        if t in ranks:
            found.append(float(ranks[t]))
        else:
            missing.append(t)
            found.append(float(size + 1))
    if missing:
        how = (
            f"not among the {len(peers.entities)} peers returned (complete list)"
            if peers.exhausted
            else f"not found within the first {len(peers.entities)} results "
            f"(search depth {SEARCH_CAP}; universe taken as {size})"
        )
        notes.append(
            f"{label}: {len(missing)} of {len(targets)} target(s) {how}; "
            f"counted as rank {size + 1}: {', '.join(missing)}."
        )
    if len(targets) > 1:
        notes.append(f"{label}: rank is the mean over {len(targets)} comparator brands.")
    mr = mean_rank(found)
    return mr, size, percentile_from_rank(mr, size), notes


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


def overlap_evidence(raw: RawData, resolution: Resolution | None = None) -> OverlapEvidence:
    """Rank-based shared-purchaser evidence in both directions (see ARCHITECTURE.md).

    Target ids come from `raw.*_target_entity_ids`; if empty, from the resolution (entity id,
    else proxy comparators). `symmetric_percentile` = mean of the available directions.
    Rank fields are the (rounded) mean ranks; percentiles use the unrounded mean.
    """
    notes: list[str] = []
    junior_targets = list(raw.junior_target_entity_ids) or _fallback_targets(resolution, "junior")
    senior_targets = list(raw.senior_target_entity_ids) or _fallback_targets(resolution, "senior")

    s2j_rank, s2j_size, s2j_pct, n1 = direction_rank(
        raw.senior_seed_junior_universe, junior_targets, "senior->junior"
    )
    j2s_rank, j2s_size, j2s_pct, n2 = direction_rank(
        raw.junior_seed_senior_universe, senior_targets, "junior->senior"
    )
    notes += n1 + n2

    pcts = [p for p in (s2j_pct, j2s_pct) if p is not None]
    symmetric = sum(pcts) / len(pcts) if pcts else None
    if len(pcts) == 1:
        notes.append("Only one direction was computable; symmetric percentile uses it alone.")
    elif not pcts:
        notes.append("Overlap could not be computed in either direction.")
    for label, pct in (("senior->junior", s2j_pct), ("junior->senior", j2s_pct)):
        if pct is not None:
            notes.append(f"{label} percentile: {pct:.3f}.")

    shared: list[dict[str, Any]] = []
    d_senior: list[dict[str, Any]] = []
    d_junior: list[dict[str, Any]] = []
    if raw.compare is None or (not raw.compare.entities and not raw.compare.tags):
        notes.append("No compare data: shared/distinct affinities are empty.")
    elif raw.compare.entities:
        shared = [_compare_row(e) for e in raw.compare.shared()]
        d_senior = [_compare_row(e) for e in raw.compare.distinct_to_a()]
        d_junior = [_compare_row(e) for e in raw.compare.distinct_to_b()]
    else:
        # Documented live shape: /v2/analysis/compare returns tags with query.score that
        # characterize how the two audiences differ. Surface them as "shared affinities".
        shared = [
            {"tag_id": t.tag_id, "name": t.name, "type": t.tag_type, "score": t.affinity}
            for t in raw.compare.tags[:15]
        ]
        notes.append("Compare returned audience tags (documented shape); no per-entity lists.")

    used_proxy = raw.used_proxy_senior or raw.used_proxy_junior
    if used_proxy:
        flags = (("senior", raw.used_proxy_senior), ("junior", raw.used_proxy_junior))
        sides = [s for s, f in flags if f]
        notes.append(f"Proxy path used for {' and '.join(sides)} (category comparators).")

    return OverlapEvidence(
        senior_to_junior_rank=round(s2j_rank) if s2j_rank is not None else None,
        senior_to_junior_universe=s2j_size,
        senior_to_junior_percentile=s2j_pct,
        junior_to_senior_rank=round(j2s_rank) if j2s_rank is not None else None,
        junior_to_senior_universe=j2s_size,
        junior_to_senior_percentile=j2s_pct,
        symmetric_percentile=symmetric,
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

    Universe = len(senior_tags). percentile = 1 - (rank-1)/universe; not found => rank None,
    percentile 0 and a note. category_affinity = the best-ranked matching tag's affinity.
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
    wanted = set(cat_ids)
    best: tuple[int, float | None, str] | None = None
    for idx, tag in enumerate(raw.senior_tags):
        if tag.tag_id not in wanted:
            continue
        r = _rank_of(tag.rank, idx)
        if best is None or r < best[0]:
            best = (r, tag.affinity, tag.name)
    if best is None:
        return BridgingEvidence(
            category_tag_ids=cat_ids,
            category_rank_among_senior_tags=None,
            senior_tag_universe=size,
            category_affinity=None,
            percentile=0.0,
            notes=[
                f"None of the junior's category tags appear among the senior's {size} taste "
                "tags; percentile set to 0."
            ],
        )
    rank, aff, name = best
    notes: list[str] = []
    if size < 50:
        notes.append(f"Small tag universe ({size} tags); percentile is coarse.")
    notes.append(f"Best-ranked category tag: {name!r} at rank {rank} of {size}.")
    return BridgingEvidence(
        category_tag_ids=cat_ids,
        category_rank_among_senior_tags=rank,
        senior_tag_universe=size,
        category_affinity=aff,
        percentile=percentile_from_rank(rank, size),
        notes=notes,
    )


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


def breadth_score(d: Demographics | None) -> float | None:
    """Breadth of appeal across the 8 buckets (6 age + 2 gender), in [0, 1].

        v_i       = bucket affinity clipped to [-1, 1]   (missing bucket = 0)
        share_pos = (# buckets with v_i > 0) / 8
        mass_pos  = sum(max(v_i, 0)) / max(sum(|v_i|), eps)     # ARCHITECTURE's weighted term
        breadth   = share_pos * mass_pos

    `mass_pos` alone (the ARCHITECTURE formula) would score a single positive spike over zeros
    as 1.0; multiplying by the unweighted share requires both "positive in many buckets" and
    "the positive side dominates in magnitude". None when no data or all buckets are 0.
    """
    if d is None or not _has_demo(d):
        return None
    v = [max(-1.0, min(1.0, x)) for x in d.age_vector() + d.gender_vector()]
    abs_mass = sum(abs(x) for x in v)
    if abs_mass <= _EPS:
        return None
    share_pos = sum(1 for x in v if x > 0) / len(v)
    mass_pos = sum(max(x, 0.0) for x in v) / max(abs_mass, _EPS)
    return _clip01(share_pos * mass_pos)


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
        top2 = sorted(range(len(AGE_BUCKETS)), key=lambda i: (-ages[i], i))[:2]
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
    if not _has_demo(demo):
        notes.append("No demographic data for the senior brand.")
    elif breadth is None:
        notes.append("All demographic buckets are zero; breadth not computable.")

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
        skew_description=skew_description(demo),
        popularity_percentile=popularity,
        heatmap_coverage=coverage,
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
    """Run only the analyses in `routing.analyses`; the others stay None."""
    data = raw if raw is not None else RawData()
    wanted = set(routing.analyses) if routing is not None else set()
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
