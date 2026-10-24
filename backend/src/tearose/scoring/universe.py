"""Universe helpers: human labels for comparison sets and a deterministic tag-picking heuristic.

`pick_category_tags` is a FALLBACK / sanity check only. The agent's own choice of category tags
(made in the `resolve` node from the `/v2/tags` menu) is authoritative and is logged separately
in `ProxyResolution.chosen_tag_ids` and the trace; this heuristic never overrides it. The graph
may log a warning when the agent's choice and this heuristic disagree completely.
"""

from __future__ import annotations

import re

from tearose.qloo.models import Tag

_STOPWORDS = frozenset(
    {
        "a", "an", "and", "or", "of", "for", "the", "in", "on", "with", "to", "by", "as", "at",
        "from", "namely", "including", "other", "related", "use", "goods", "services", "products",
        "product", "class", "retail", "store", "stores", "featuring", "being", "such",
    }
)  # fmt: skip

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _singular(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("ches", "shes", "sses", "xes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens, stopwords removed, crudely singularized."""
    return [_singular(t) for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


def _is_category(tag: Tag) -> bool:
    return "category" in (tag.tag_type or "").lower()


def build_universe_description(tags: list[Tag]) -> str:
    """Short human label for a universe, e.g. [Tag(name="Pet Supply")] -> "pet supply brands".

    Uses up to two tag names (in the given order), lowercased, joined with " / ".
    Empty input -> "brands (unspecified category)".
    """
    names: list[str] = []
    for tag in tags:
        name = " ".join((tag.name or "").split()).strip().lower()
        if name and name not in names:
            names.append(name)
        if len(names) == 2:
            break
    if not names:
        return "brands (unspecified category)"
    label = " / ".join(names)
    if label.endswith(("brands", "brand")):
        return label if label.endswith("brands") else label + "s"
    return f"{label} brands"


def pick_category_tags(tags: list[Tag], goods_phrase: str, max_n: int = 3) -> list[Tag]:
    """Deterministically pick up to `max_n` tags whose names best match `goods_phrase`.

    Score per tag: number of distinct (singularized, stopword-free) goods tokens that appear in
    the tag name. Only tags with score > 0 qualify. Ties break, in order, by: category-type tags
    first (`"category"` in `tag_type`), then broader tags (fewer name tokens), then the original
    menu order. Returns [] when nothing overlaps - the caller then relies on the agent's choice.
    """
    if max_n <= 0 or not tags:
        return []
    goods = set(tokenize(goods_phrase or ""))
    if not goods:
        return []
    scored: list[tuple[int, int, int, int, Tag]] = []
    for idx, tag in enumerate(tags):
        name_tokens = tokenize(tag.name or "")
        overlap = len(goods & set(name_tokens))
        if overlap == 0:
            continue
        scored.append((-overlap, 0 if _is_category(tag) else 1, len(name_tokens), idx, tag))
    scored.sort(key=lambda s: s[:4])
    return [s[4] for s in scored[:max_n]]
