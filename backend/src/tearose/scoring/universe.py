"""Universe helpers: human labels for comparison sets and a deterministic tag-picking heuristic.

`pick_category_tags` is a FALLBACK / sanity check only. The agent's own choice of category tags
(made in the `resolve` node from the brand taxonomy or the `/v2/tags` menu) is authoritative
and is logged separately in `ProxyResolution.chosen_tag_ids` and the trace; this heuristic
never overrides it. The graph may log a warning when the agent's choice and this heuristic
disagree completely. Brand-genre tags (urn:tag:genre:brand) are preferred over all others.
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


GENRE_BRAND = "urn:tag:genre:brand"


def _is_category(tag: Tag) -> bool:
    return "category" in (tag.tag_type or "").lower()


def is_brand_genre(tag: Tag) -> bool:
    """A node of Qloo's brand-category taxonomy (urn:tag:genre:brand[:...])."""
    return (tag.tag_type or "").startswith(GENRE_BRAND) or tag.tag_id.startswith(GENRE_BRAND)


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
    the tag name. Only tags with score > 0 qualify. Brand-genre tags (`urn:tag:genre:brand...`,
    the clean category taxonomy) rank before every other tag; within each group: higher score,
    then category-type tags (`"category"` in `tag_type`), then broader tags (fewer name tokens),
    then the original menu order. Returns [] when nothing overlaps - the caller then relies on
    the agent's choice.
    """
    if max_n <= 0 or not tags:
        return []
    goods = set(tokenize(goods_phrase or ""))
    if not goods:
        return []
    scored: list[tuple[int, int, int, int, int, Tag]] = []
    for idx, tag in enumerate(tags):
        name_tokens = tokenize(tag.name or "")
        overlap = len(goods & set(name_tokens))
        if overlap == 0:
            continue
        scored.append(
            (
                0 if is_brand_genre(tag) else 1,
                -overlap,
                0 if _is_category(tag) else 1,
                len(name_tokens),
                idx,
                tag,
            )
        )
    scored.sort(key=lambda s: s[:5])
    return [s[5] for s in scored[:max_n]]


# --------------------------------------------------------------------------------------
# Universe rule (harness v2, also the product path): the brand's OWN category
# --------------------------------------------------------------------------------------
#
# A brand's universe is the category the brand IS in, read from its own urn:tag:genre:brand
# tags on the /search result (a sneaker brand: fashion, fashion:footwear,
# fashion:footwear:sneakers). The pre-registered v1 rule took the top insights tags seeded by
# the brand, which describe what the brand's AUDIENCE likes (a sneaker brand came out as
# "Food & Beverage"); that rule survives only as the fallback for brands without own tags.

OWN_TAGS_SOURCE = "entity own tags"
INSIGHTS_FALLBACK_SOURCE = "insights tags (fallback)"
OWN_TAGS_MAX = 3
INSIGHTS_TAGS_TOP = 5
_GENRE_PREFIX = GENRE_BRAND + ":"


def genre_depth(tag_id: str) -> int:
    """Segments below urn:tag:genre:brand (fashion = 1, fashion:footwear = 2); 0 otherwise."""
    if not tag_id.startswith(_GENRE_PREFIX):
        return 0
    return len([p for p in tag_id[len(_GENRE_PREFIX) :].split(":") if p])


def _display(tag: Tag) -> Tag:
    """'Other' leaves get their parent in the name ("Other footwear") so labels stay readable."""
    name = " ".join((tag.name or "").split())
    if name.casefold() in {"", "other"}:
        segs = tag.tag_id[len(_GENRE_PREFIX) :].split(":")
        parent = segs[-2].replace("_", " ") if len(segs) > 1 else ""
        leaf = segs[-1].replace("_", " ")
        label = f"Other {parent}".strip() if leaf == "other" else (name or leaf)
        return tag.model_copy(update={"name": label})
    return tag


def fold_other(tag: Tag, by_id: dict[str, Tag] | None = None) -> Tag:
    """A catch-all leaf ("...:whiskey:other") stands for its parent ("...:whiskey"): the
    parent's tag from `by_id` when present, else a tag named after the parent segment.
    A top-level "other" (no parent below urn:tag:genre:brand) and every other node: unchanged."""
    segs = tag.tag_id[len(_GENRE_PREFIX) :].split(":") if genre_depth(tag.tag_id) >= 2 else []
    if not segs or segs[-1] != "other":
        return tag
    parent_id = _GENRE_PREFIX + ":".join(segs[:-1])
    if by_id and parent_id in by_id:
        return by_id[parent_id]
    return tag.model_copy(
        update={"tag_id": parent_id, "name": segs[-2].replace("_", " ").capitalize()}
    )


def own_category_tags(tags: list[Tag], max_n: int = OWN_TAGS_MAX) -> list[Tag]:
    """The most specific brand-genre nodes among an entity's own tags.

    Keep tags whose id is a urn:tag:genre:brand:* node; replace a catch-all "other" leaf by its
    parent (whiskey:other -> whiskey, so the universe is all whiskey brands, not the few
    "other whiskey" ones); drop any node that is an ancestor of another node in the set; prefer
    depth >= 2 (a lone top family such as "fashion" is used only when nothing deeper exists);
    keep up to `max_n` in the response order. [] when the entity carries no brand-genre tag
    (the caller then falls back to insights tags).
    """
    by_id = {t.tag_id: t for t in tags if genre_depth(t.tag_id) >= 1}
    seen: set[str] = set()
    genre: list[Tag] = []
    for raw in tags:
        if genre_depth(raw.tag_id) < 1:
            continue
        t = fold_other(raw, by_id)
        if t.tag_id not in seen:
            seen.add(t.tag_id)
            genre.append(t)
    leaves = [t for t in genre if not any(o.tag_id.startswith(t.tag_id + ":") for o in genre)]
    deep = [t for t in leaves if genre_depth(t.tag_id) >= 2]
    return [_display(t) for t in (deep or leaves)[:max_n]]


def is_universe_tag(t: Tag) -> bool:
    kind = (t.tag_type or "").lower() or t.tag_id.lower()
    return "category" in kind or "genre" in kind


def insights_universe_tags(tags: list[Tag], top: int = INSIGHTS_TAGS_TOP) -> list[Tag]:
    """v1 rule, now the fallback: top `top` brand-genre insights tags seeded by the brand
    (any category/genre tag when the response has no brand-genre tag)."""
    genre = [t for t in tags if is_brand_genre(t)]
    return (genre or [t for t in tags if is_universe_tag(t)])[:top]
