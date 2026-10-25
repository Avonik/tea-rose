"""Step 2, `resolve`: mapping.csv -> resolved.json. Qloo: /search, /v2/tags, insights tags.

Deterministic rules (no model):
- Entity pick: /search(query, types=<side type>, take=10), the side type coming from the
  mapping's senior_type / junior_type column ("brand" unless pre-registered otherwise, e.g.
  "artist" for Aqua); the candidate is chosen by `qloo.names.pick_by_name`: normalised exact
  name match, else a strict fuzzy rule, else MISS (never "the first result": /search returns
  unrelated top hits for small brands). The rule ("exact" | "fuzzy:<ratio>" | "miss"), all
  candidate names and the type are recorded.
- Same entity on both sides (e.g. a junior query that only finds the senior) -> the junior is
  treated as not found.
- Not found -> proxy path: the goods phrase is mapped onto Qloo's brand taxonomy
  (urn:tag:genre:brand, harvested once via 26 letter queries) by `qloo.taxonomy.map_goods_phrase`:
  up to 3 nodes, each labelled exact | partial | nearest. Only when the taxonomy is unavailable
  or nothing maps does the old last resort run: the phrase VERBATIM to free-text /v2/tags, then
  one shortened phrase, then `pick_category_tags` (first menu tag when nothing overlaps).
- Universe tags of a resolved brand (harness v2, `scoring.universe.own_category_tags`): the
  brand's OWN urn:tag:genre:brand tags from its /search result, most specific nodes only (an
  ancestor of another node is dropped), depth >= 2 preferred, up to 3; source
  "entity own tags". Only when the entity carries no brand-genre tag: the v1 rule, insights tags
  seeded by the brand restricted to filter.tag.types=urn:tag:genre:brand (take 50), top 5
  (source "insights tags (fallback)"); v1 used that rule for every brand and so measured what
  the brand's AUDIENCE likes, not what the brand is. If that is empty too, the goods phrase
  mapping above (recorded as the source).
"""

from __future__ import annotations

import re
from typing import Any

from tearose.eval.backtest import HARNESS_VERSION
from tearose.eval.backtest.common import DEFAULT_ENTITY_TYPE, Recorder, entity_urn
from tearose.qloo.models import Entity, Tag
from tearose.qloo.names import pick_by_name
from tearose.qloo.taxonomy import (
    NEAREST_NOTE,
    TaxonomyNode,
    best_fit,
    load_brand_taxonomy,
    map_goods_phrase,
)
from tearose.scoring.universe import (
    INSIGHTS_FALLBACK_SOURCE,
    OWN_TAGS_SOURCE,
    genre_depth,
    insights_universe_tags,
    own_category_tags,
    pick_category_tags,
)

SEARCH_TAKE = 10
TAGS_TAKE = 50
UNIVERSE_TOP = 5  # insights-tags fallback only
PROXY_TAGS_TOP = 3


def pick_entity(query: str, results: list[Entity]) -> tuple[Entity | None, str]:
    """(entity, rule): rule is "exact", "fuzzy:<ratio>", "miss", or "no results"."""
    if not results:
        return None, "no results"
    return pick_by_name(query, results)


def shorten_phrase(phrase: str) -> str | None:
    """First clause without parentheticals, last two words; None when nothing shorter."""
    p = re.sub(r"\(.*?\)", " ", phrase)
    first = re.split(r"[;,:/]|\band\b|\bor\b|\bnamely\b", p, flags=re.I)[0]
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", first)
    short = " ".join(words[-2:]) if words else ""
    if not short or short.casefold() == phrase.strip().casefold():
        return None
    return short


def _tag_dict(t: Tag) -> dict[str, Any]:
    return {"id": t.tag_id, "name": t.name, "type": t.tag_type}


async def brand_taxonomy(rec: Recorder) -> list[TaxonomyNode]:
    """The brand taxonomy (memoised per client), logged as one query entry per use."""
    try:
        nodes = await load_brand_taxonomy(rec.client)
    except Exception as exc:  # noqa: BLE001 - degrade to free-text /v2/tags
        status = getattr(exc, "status", None)
        if status in (401, 403):
            raise
        rec.notes.append(f"brand taxonomy unavailable ({status}): {repr(exc)[:160]}")
        return []
    rec.queries.append(
        {
            "call": "brand_taxonomy",
            "endpoint": "/v2/tags",
            "params": {"filter.query": "a..z", "filter.tag.types": "urn:tag:genre:brand",
                       "take": 50},
            "result_count": len(nodes),
        }
    )  # fmt: skip
    return nodes


async def tags_for_phrase(rec: Recorder, phrase: str) -> dict[str, Any]:
    """Goods phrase -> brand-taxonomy nodes (exact|partial|nearest); free-text /v2/tags only as
    the last resort."""
    taxonomy = await brand_taxonomy(rec) if phrase.strip() else []
    matches = map_goods_phrase(phrase, taxonomy)
    if matches:
        fit = best_fit([m.fit for m in matches])
        return {
            "goods_phrase": phrase,
            "phrases_tried": [phrase],
            "tag_options": [m.as_dict() for m in matches],
            "chosen_tag_ids": [m.node.tag_id for m in matches],
            "chosen_tag_names": [m.node.name for m in matches],
            "fit": fit,
            "fit_note": NEAREST_NOTE if fit == "nearest" else None,
            "rule": f"brand taxonomy ({len(taxonomy)} nodes) -> map_goods_phrase",
        }
    return await _free_text_tags(rec, phrase, taxonomy_size=len(taxonomy))


async def _free_text_tags(rec: Recorder, phrase: str, taxonomy_size: int) -> dict[str, Any]:
    """Last resort: /v2/tags on the verbatim phrase (then one shortened phrase)."""
    tried: list[str] = []
    options: list[Tag] = []
    used = phrase
    if phrase.strip():
        tried.append(phrase)
        options = list(await rec.tags_search(phrase))
        short = shorten_phrase(phrase)
        if not options and short:
            tried.append(short)
            options = list(await rec.tags_search(short))
            used = short
    chosen = pick_category_tags(options, used, max_n=PROXY_TAGS_TOP)
    rule = "pick_category_tags (keyword overlap)"
    if not chosen and options:
        chosen, rule = options[:1], "first tag of the menu (no keyword overlap)"
    fit = None
    if chosen:
        fit = "partial" if rule.startswith("pick_category_tags") else "nearest"
    prefix = (
        f"no brand-taxonomy match ({taxonomy_size} nodes); free-text /v2/tags -> "
        if taxonomy_size
        else "brand taxonomy unavailable; free-text /v2/tags -> "
    )
    return {
        "goods_phrase": phrase,
        "phrases_tried": tried,
        "tag_options": [_tag_dict(t) for t in options],
        "chosen_tag_ids": [t.tag_id for t in chosen],
        "chosen_tag_names": [t.name for t in chosen],
        "fit": fit,
        "fit_note": NEAREST_NOTE if fit == "nearest" else None,
        "rule": prefix + (rule if chosen else "no tags returned"),
    }


async def resolve_side(
    rec: Recorder,
    query: str,
    goods_phrase: str,
    avoid_entity_id: str | None = None,
    entity_type: str = DEFAULT_ENTITY_TYPE,
) -> dict[str, Any]:
    notes: list[str] = []
    entity_type = (entity_type or DEFAULT_ENTITY_TYPE).strip() or DEFAULT_ENTITY_TYPE
    urn = entity_urn(entity_type)
    results = list(await rec.search(query, take=SEARCH_TAKE, types=urn)) if query.strip() else []
    entity, rule = pick_entity(query, results)
    if entity is not None and avoid_entity_id and entity.entity_id == avoid_entity_id:
        notes.append(
            f"search for {query!r} picked the senior's own entity ({entity.name}); "
            "treated as not found"
        )
        entity, rule = None, "picked the other side's entity"
    side: dict[str, Any] = {
        "query": query,
        "type": entity_type,
        "type_urn": urn,
        "goods_phrase": goods_phrase,
        "candidates_considered": [e.name for e in results],
        "pick_rule": rule,
        "entity_id": entity.entity_id if entity else None,
        "entity_name": entity.name if entity else None,
        "popularity": entity.popularity if entity else None,
        "proxy": None,
        "universe": None,
        "notes": notes,
    }
    if entity is None:
        proxy = await tags_for_phrase(rec, goods_phrase)
        side["proxy"] = proxy
        if proxy["chosen_tag_ids"]:
            side["status"] = "proxy"
            side["universe"] = {
                "tag_ids": proxy["chosen_tag_ids"],
                "tag_names": proxy["chosen_tag_names"],
                "source": "proxy tags (goods phrase -> /v2/tags)",
            }
        else:
            side["status"] = "unresolved"
            notes.append("no brand and no tags for the goods phrase")
        return side

    side["status"] = "resolved"
    own_genre = [t.tag_id for t in entity.tag_details if genre_depth(t.tag_id) >= 1]
    own = own_category_tags(entity.tag_details)
    if own:
        side["universe"] = {
            "tag_ids": [t.tag_id for t in own],
            "tag_names": [t.name for t in own],
            "source": OWN_TAGS_SOURCE,
            "own_genre_tag_ids": own_genre,
        }
        return side
    tags = list(await rec.insights_tags([entity.entity_id], take=TAGS_TAKE))
    uni = insights_universe_tags(tags, top=UNIVERSE_TOP)
    if uni:
        side["universe"] = {
            "tag_ids": [t.tag_id for t in uni],
            "tag_names": [t.name for t in uni],
            "source": INSIGHTS_FALLBACK_SOURCE,
        }
    else:
        fb = await tags_for_phrase(rec, goods_phrase)
        if fb["chosen_tag_ids"]:
            side["universe"] = {
                "tag_ids": fb["chosen_tag_ids"],
                "tag_names": fb["chosen_tag_names"],
                "source": "fallback: goods phrase -> " + fb["rule"],
                "tag_options": fb["tag_options"],
            }
        else:
            notes.append("no category/genre tags for the brand and none for its goods phrase")
    return side


async def resolve_case(rec: Recorder, row: dict[str, str]) -> dict[str, Any]:
    senior = await resolve_side(
        rec,
        row["senior_query"],
        row["senior_goods_phrase"],
        entity_type=row.get("senior_type") or DEFAULT_ENTITY_TYPE,
    )
    junior = await resolve_side(
        rec,
        row["junior_query"],
        row["junior_goods_phrase"],
        avoid_entity_id=senior["entity_id"],
        entity_type=row.get("junior_type") or DEFAULT_ENTITY_TYPE,
    )
    return {
        "case_id": row["case_id"],
        "senior": senior,
        "junior": junior,
        "queries": rec.take_queries(),
        "notes": rec.take_notes(),
    }


def selected_rows(rows: list[dict[str, str]], include_all: bool) -> list[dict[str, str]]:
    """Rows that enter at least one metric (unless include_all): saves Qloo calls."""
    if include_all:
        return rows
    return [r for r in rows if "yes" in (r["include_relatedness"], r["include_fame"])]


async def run(
    rec: Recorder, rows: list[dict[str, str]], mode: str, mapping_sha256: str | None
) -> dict[str, Any]:
    cases = []
    for row in rows:
        cases.append(await resolve_case(rec, row))
    return {
        "harness_version": HARNESS_VERSION,
        "qloo_mode": mode,
        "mapping_sha256": mapping_sha256,
        "cases": cases,
    }


def summarize(doc: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, int] = {}
    for c in doc["cases"]:
        for side in ("senior", "junior"):
            k = f"{side}_{c[side]['status']}"
            out[k] = out.get(k, 0) + 1
    return {
        "cases": len(doc["cases"]),
        **dict(sorted(out.items())),
        "queries": sum(len(c["queries"]) for c in doc["cases"]),
    }
