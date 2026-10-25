"""Step 2, `resolve`: mapping.csv -> resolved.json. Qloo: /search, /v2/tags, insights tags.

Deterministic rules (no model):
- Entity pick: /search(query, types=<side type>, take=10), the side type coming from the
  mapping's senior_type / junior_type column ("brand" unless pre-registered otherwise, e.g.
  "artist" for Aqua); the first result whose name equals the query case-insensitively, else the
  first result. All candidate names and the type are recorded.
- Same entity on both sides (e.g. a junior query that only finds the senior) -> the junior is
  treated as not found.
- Not found -> proxy path: the goods phrase goes VERBATIM to /v2/tags; if that returns nothing,
  one shortened phrase is tried (first clause, parentheticals removed, last two words).
  `pick_category_tags` (scoring/universe.py) picks up to 3 tags; when it finds no keyword
  overlap, the first tag of the menu is used. Menu, phrases tried and choice are recorded.
- Universe tags of a resolved brand: insights tags seeded by the brand (take 50), keeping tags
  whose type contains "category" or "genre", top 5 in response order. If none, fall back to
  /v2/tags on the brand's goods phrase + pick_category_tags (recorded as the source).
"""

from __future__ import annotations

import re
from typing import Any

from tearose.eval.backtest.common import DEFAULT_ENTITY_TYPE, Recorder, entity_urn
from tearose.qloo.models import Entity, Tag
from tearose.scoring.universe import pick_category_tags

SEARCH_TAKE = 10
TAGS_TAKE = 50
UNIVERSE_TOP = 5
PROXY_TAGS_TOP = 3


def pick_entity(query: str, results: list[Entity]) -> tuple[Entity | None, str]:
    """(entity, rule): exact case-insensitive name match first, else the first result."""
    if not results:
        return None, "no results"
    q = query.strip().casefold()
    for e in results:
        if e.name.strip().casefold() == q:
            return e, "exact name match"
    return results[0], "first result (no exact name match)"


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


def is_universe_tag(t: Tag) -> bool:
    kind = (t.tag_type or "").lower() or t.tag_id.lower()
    return "category" in kind or "genre" in kind


async def tags_for_phrase(rec: Recorder, phrase: str) -> dict[str, Any]:
    """/v2/tags on the verbatim phrase (then one shortened phrase) -> menu + deterministic pick."""
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
    return {
        "goods_phrase": phrase,
        "phrases_tried": tried,
        "tag_options": [_tag_dict(t) for t in options],
        "chosen_tag_ids": [t.tag_id for t in chosen],
        "chosen_tag_names": [t.name for t in chosen],
        "rule": rule if chosen else "no tags returned",
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
    tags = list(await rec.insights_tags([entity.entity_id], take=TAGS_TAKE))
    uni = [t for t in tags if is_universe_tag(t)][:UNIVERSE_TOP]
    if uni:
        side["universe"] = {
            "tag_ids": [t.tag_id for t in uni],
            "tag_names": [t.name for t in uni],
            "source": "brand's own category/genre tags (insights tags, top 5)",
        }
    else:
        fb = await tags_for_phrase(rec, goods_phrase)
        if fb["chosen_tag_ids"]:
            side["universe"] = {
                "tag_ids": fb["chosen_tag_ids"],
                "tag_names": fb["chosen_tag_names"],
                "source": "fallback: goods phrase -> /v2/tags -> " + fb["rule"],
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
    return {"qloo_mode": mode, "mapping_sha256": mapping_sha256, "cases": cases}


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
