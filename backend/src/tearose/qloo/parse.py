"""Tolerant parsers from raw Qloo JSON into normalized models.

Field names follow docs/qloo-api-notes.md. Where the docs are silent we accept several
plausible spellings. After the Monday live test, tighten these and delete the fallbacks.
"""

from __future__ import annotations

from typing import Any

from tearose.qloo.models import (
    CompareEntity,
    CompareResult,
    Demographics,
    Entity,
    HeatmapPoint,
    Tag,
)


def _first(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _results(raw: dict[str, Any]) -> dict[str, Any]:
    """Insights responses wrap payloads in {"success": true, "results": {...}}."""
    r = raw.get("results", raw)
    return r if isinstance(r, dict) else {"entities": r}


def _norm_affinity(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v / 100.0 if v > 1.0 else v


def _query_block(item: dict[str, Any]) -> dict[str, Any]:
    q = item.get("query")
    return q if isinstance(q, dict) else {}


def _explainability(q: dict[str, Any]) -> dict[str, float]:
    ex = q.get("explainability")
    if not isinstance(ex, dict):
        return {}
    # Documented: explainability -> {"signal.interests.entities": [{"entity_id":..,"score":..}]}
    # Fallback: a flat {entity_id: score} map.
    sig = ex.get("signal.interests.entities")
    out: dict[str, float] = {}
    if isinstance(sig, list):
        for s in sig:
            if isinstance(s, dict) and "entity_id" in s:
                try:
                    out[str(s["entity_id"])] = float(_first(s, "score", "affinity", default=0.0))
                except (TypeError, ValueError):
                    continue
        return out
    for k, v in ex.items():
        if isinstance(v, int | float):
            out[str(k)] = float(v)
    return out


def parse_entity(item: dict[str, Any], rank: int | None = None) -> Entity:
    q = _query_block(item)
    tags_raw = item.get("tags") or []
    tag_ids = [
        str(_first(t, "tag_id", "id", default=t)) if isinstance(t, dict) else str(t)
        for t in tags_raw
    ]
    types = item.get("types") or []
    subtype = _first(item, "subtype", default=(types[0] if types else None))
    return Entity(
        entity_id=str(_first(item, "entity_id", "id")),
        name=str(_first(item, "name", default="")),
        subtype=subtype,
        popularity=_first(item, "popularity"),
        affinity=_norm_affinity(_first(q, "affinity", default=item.get("affinity"))),
        rank=rank,
        explainability=_explainability(q),
        tags=tag_ids,
        properties=item.get("properties") or {},
        disambiguation=_first(item, "disambiguation"),
    )


def parse_entities(raw: dict[str, Any]) -> list[Entity]:
    res = _results(raw)
    items = _first(res, "entities", "results", default=[]) or []
    return [parse_entity(it, rank=i + 1) for i, it in enumerate(items) if isinstance(it, dict)]


def parse_search(raw: dict[str, Any]) -> list[Entity]:
    """/search returns {"results": [ {...entity...} ]}."""
    items = raw.get("results", raw.get("entities", [])) or []
    if isinstance(items, dict):
        items = items.get("entities", [])
    return [parse_entity(it, rank=i + 1) for i, it in enumerate(items) if isinstance(it, dict)]


def parse_tag(item: dict[str, Any], rank: int | None = None) -> Tag:
    """Tags come in two spellings: /v2/tags uses id/type; insights and compare use
    tag_id/subtype, with the score under query.affinity (insights) or query.score (compare)."""
    q = _query_block(item)
    types = item.get("types") or []
    subtype = item.get("subtype")
    ttype = item.get("type")
    # Prefer the specific subtype over the generic "urn:tag" type.
    tag_type = subtype or (ttype if ttype and ttype != "urn:tag" else None) or (types[0] if types else ttype)
    return Tag(
        tag_id=str(_first(item, "tag_id", "id")),
        name=str(_first(item, "name", default="")),
        tag_type=tag_type,
        affinity=_norm_affinity(_first(q, "affinity", "score", default=item.get("affinity"))),
        rank=rank,
    )


def parse_tags(raw: dict[str, Any]) -> list[Tag]:
    res = _results(raw)
    items = _first(res, "tags", "results", default=[]) or []
    return [parse_tag(it, rank=i + 1) for i, it in enumerate(items) if isinstance(it, dict)]


def parse_heatmap(raw: dict[str, Any]) -> list[HeatmapPoint]:
    res = _results(raw)
    items = _first(res, "heatmap", "points", default=[]) or []
    out: list[HeatmapPoint] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        loc = it.get("location") or it
        q = _query_block(it) or it
        try:
            out.append(
                HeatmapPoint(
                    latitude=float(_first(loc, "latitude", "lat")),
                    longitude=float(_first(loc, "longitude", "lon", "lng")),
                    geohash=_first(loc, "geohash"),
                    affinity=_norm_affinity(_first(q, "affinity")),
                    affinity_rank=_first(q, "affinity_rank"),
                    popularity=_first(q, "popularity"),
                    label=_first(loc, "name", "label"),
                )
            )
        except (TypeError, ValueError):
            continue
    return out


def parse_demographics(raw: dict[str, Any]) -> Demographics:
    res = _results(raw)
    items = _first(res, "demographics", default=[]) or []
    if isinstance(items, dict):
        items = [items]
    age: dict[str, float] = {}
    gender: dict[str, float] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        q = _query_block(it) or it
        for k, v in (q.get("age") or {}).items():
            age[str(k)] = float(v)
        for k, v in (q.get("gender") or {}).items():
            gender[str(k)] = float(v)
    return Demographics(age=age, gender=gender)


def parse_compare(raw: dict[str, Any]) -> CompareResult:
    """Documented shape: results.tags[{tag_id, name, subtype, query{score}}] — the endpoint
    returns TAGS that characterize how the two groups differ. Entities are parsed too in case
    the live API adds them; today that list is expected to be empty."""
    res = _results(raw)
    ents: list[CompareEntity] = []
    for it in _first(res, "entities", default=[]) or []:
        if not isinstance(it, dict):
            continue
        q = _query_block(it)
        a = _norm_affinity(_first(q.get("a") or {}, "affinity", default=q.get("a_affinity")))
        b = _norm_affinity(_first(q.get("b") or {}, "affinity", default=q.get("b_affinity")))
        delta = _first(q, "delta")
        if delta is None and a is not None and b is not None:
            delta = a - b
        types = it.get("types") or []
        ents.append(
            CompareEntity(
                entity_id=str(_first(it, "entity_id", "id")),
                name=str(_first(it, "name", default="")),
                subtype=_first(it, "subtype", default=(types[0] if types else None)),
                a_affinity=a,
                b_affinity=b,
                delta=float(delta) if delta is not None else None,
            )
        )
    tags = [parse_tag(t, i + 1) for i, t in enumerate(_first(res, "tags", default=[]) or [])]
    return CompareResult(entities=ents, tags=tags)
