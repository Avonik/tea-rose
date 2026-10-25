"""Qloo's brand-category taxonomy (urn:tag:genre:brand) and a deterministic goods mapper.

Live spike facts: the taxonomy is a tree of ~177 nodes in 27 top families, depth 1-4
(e.g. urn:tag:genre:brand:wine_and_spirits:spirits:whiskey:bourbon). /v2/tags lists nothing
without filter.query, matches the query against node NAMES, and returns < 50 nodes for any single
letter, so 26 letter queries harvest the whole tree. Free-text goods phrases mostly miss
("dog toy", "handbags" -> 0), and there is no pet-supplies or toy node at all: a dog-toy maker's
nearest node is food_and_beverage:pet_food, which must be reported as an approximation.

`map_goods_phrase` scores nodes by token overlap with the node name and path plus a small
synonym table and labels each match:
- "exact":   the phrase's head noun (last word of its first clause) names the node, literally or
             through an equivalent synonym (whisky/bourbon -> whiskey);
- "partial": some phrase word names the node, but not the head noun ("luxury handbags" ->
             Luxury);
- "nearest": only an approximate synonym links them ("squeaky dog chew toy" -> Pet Food):
             no exact match exists in Qloo's brand taxonomy.
"""

from __future__ import annotations

import contextlib
import re
import string
import weakref
from dataclasses import dataclass
from typing import Any, Literal

from tearose.qloo.client import GENRE_BRAND

Fit = Literal["exact", "partial", "nearest"]
FIT_ORDER: dict[str, int] = {"exact": 0, "partial": 1, "nearest": 2}
HARVEST_TAKE = 50
MAX_MATCHES = 3
NEAREST_NOTE = "nearest category, no exact match in Qloo's brand taxonomy"


@dataclass(frozen=True)
class TaxonomyNode:
    tag_id: str  # urn:tag:genre:brand:<seg>[:<seg>...]
    name: str
    path: tuple[str, ...]  # segments below urn:tag:genre:brand
    depth: int  # len(path), 1 = top family
    parent: str | None  # parent tag_id, None for a top family

    @property
    def slug(self) -> str:
        return self.path[-1] if self.path else ""

    @property
    def path_label(self) -> str:
        return "/".join(self.path)


@dataclass(frozen=True)
class ProxyMatch:
    node: TaxonomyNode
    fit: Fit
    score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.node.tag_id,
            "name": self.node.name,
            "path": self.node.path_label,
            "fit": self.fit,
            "score": self.score,
        }


def node_from_tag_id(tag_id: str, name: str) -> TaxonomyNode | None:
    prefix = GENRE_BRAND + ":"
    if not tag_id.startswith(prefix):
        return None
    path = tuple(p for p in tag_id[len(prefix) :].split(":") if p)
    if not path:
        return None
    parent = prefix + ":".join(path[:-1]) if len(path) > 1 else None
    return TaxonomyNode(tag_id=tag_id, name=name, path=path, depth=len(path), parent=parent)


# --- harvesting ------------------------------------------------------------------------

_MEMO: weakref.WeakKeyDictionary[Any, list[TaxonomyNode]] = weakref.WeakKeyDictionary()


async def load_brand_taxonomy(client: Any, *, refresh: bool = False) -> list[TaxonomyNode]:
    """All urn:tag:genre:brand nodes via 26 letter queries to /v2/tags, deduped by tag_id,
    sorted by path. Memoised per client object (the LiveClient cache already makes repeat HTTP
    calls free). Errors propagate; callers decide how to degrade."""
    if not refresh:
        try:
            if client in _MEMO:
                return _MEMO[client]
        except TypeError:  # not weak-referenceable: no memo
            pass
    nodes: dict[str, TaxonomyNode] = {}
    for letter in string.ascii_lowercase:
        tags, _ = await client.tags_search(letter, tag_types=[GENRE_BRAND], take=HARVEST_TAKE)
        for t in tags:
            node = node_from_tag_id(t.tag_id, t.name)
            if node is not None:
                nodes.setdefault(node.tag_id, node)
    out = sorted(nodes.values(), key=lambda n: n.path)
    with contextlib.suppress(TypeError):  # not weak-referenceable: no memo
        _MEMO[client] = out
    return out


def taxonomy_menu(taxonomy: list[TaxonomyNode]) -> list[str]:
    """Compact lines for a prompt: "wine_and_spirits/spirits/whiskey = Whiskey"."""
    return [f"{n.path_label} = {n.name}" for n in taxonomy]


# --- mapping ---------------------------------------------------------------------------

_STOP = frozenset(
    {"a", "an", "and", "or", "of", "for", "the", "in", "on", "with", "to", "by", "as", "at",
     "from", "namely", "including", "other", "related", "use", "goods", "services", "product",
     "products", "featuring", "being", "such", "brand", "brands", "line", "type", "kind"}
)  # fmt: skip
_TOKEN = re.compile(r"[a-z0-9]+")

# phrase token (singular) -> [(node slug, strength)]. "exact" = an equivalent or narrower term
# for that node; "nearest" = a stand-in because the taxonomy has no node for the goods.
SYNONYMS: dict[str, list[tuple[str, Fit]]] = {
    "whisky": [("whiskey", "exact")],
    "bourbon": [("bourbon", "exact"), ("whiskey", "exact")],
    "scotch": [("scotch", "exact"), ("whiskey", "exact")],
    "rye": [("whiskey", "exact")],
    "liquor": [("spirits", "exact")],
    "tequila": [("tequila", "exact"), ("spirits", "exact")],
    "gin": [("gin", "exact"), ("spirits", "exact")],
    "rum": [("rum", "exact"), ("spirits", "exact")],
    "ale": [("beer", "exact")],
    "lager": [("beer", "exact")],
    "champagne": [("wine", "exact")],
    "coffee": [("coffee_and_tea", "exact"), ("coffee", "exact")],
    "espresso": [("coffee_and_tea", "exact"), ("coffee", "exact")],
    "tea": [("coffee_and_tea", "exact")],
    "cafe": [("coffee_and_tea", "nearest")],
    "dog": [("pet_food", "nearest")],
    "puppy": [("pet_food", "nearest")],
    "cat": [("pet_food", "nearest")],
    "kitten": [("pet_food", "nearest")],
    "pet": [("pet_food", "nearest")],
    "sneaker": [("sneakers", "exact"), ("footwear", "exact")],
    "shoe": [("footwear", "exact"), ("sneakers", "nearest")],
    "boot": [("footwear", "exact")],
    "trainer": [("sneakers", "exact"), ("footwear", "exact")],
    "handbag": [("handbags", "exact"), ("accessories", "nearest"), ("luxury", "nearest")],
    "purse": [("handbags", "exact"), ("accessories", "nearest"), ("luxury", "nearest")],
    "wallet": [("accessories", "nearest")],
    "jewelry": [("jewelry", "exact"), ("accessories", "nearest")],
    "jewellery": [("jewelry", "exact"), ("accessories", "nearest")],
    "watch": [("watches", "exact"), ("accessories", "nearest")],
    "apparel": [("apparel", "exact"), ("clothing", "exact"), ("fashion", "nearest")],
    "clothing": [("clothing", "exact"), ("apparel", "exact"), ("fashion", "nearest")],
    "garment": [("clothing", "exact"), ("apparel", "exact"), ("fashion", "nearest")],
    "shirt": [("apparel", "nearest"), ("clothing", "nearest"), ("fashion", "nearest")],
    "restaurant": [("restaurants", "exact"), ("dining", "exact")],
    "burger": [("fast_food", "exact"), ("dining", "nearest")],
    "hamburger": [("fast_food", "exact"), ("dining", "nearest")],
    "pizza": [("fast_food", "nearest"), ("dining", "nearest")],
    "cosmetic": [("cosmetics", "exact"), ("beauty", "exact"), ("health_and_beauty", "nearest")],
    "makeup": [("cosmetics", "exact"), ("beauty", "exact"), ("health_and_beauty", "nearest")],
    "skincare": [("skincare", "exact"), ("health_and_beauty", "nearest")],
    "perfume": [("fragrance", "exact"), ("health_and_beauty", "nearest")],
    "phone": [("electronics", "nearest")],
    "computer": [("electronics", "nearest")],
    "electronic": [("electronics", "exact")],
    "car": [("automotive", "exact")],
    "vehicle": [("automotive", "exact")],
    "hotel": [("hotels", "exact"), ("travel", "nearest")],
    "airline": [("airlines", "exact"), ("travel", "nearest")],
    "grocery": [("grocery", "exact"), ("retail", "nearest")],
    "supermarket": [("grocery", "exact"), ("retail", "nearest")],
    "snack": [("snacks", "exact")],
    "chip": [("snacks", "nearest")],
    "candy": [("candy", "exact"), ("snacks", "nearest")],
}
# two-word phrases (singularised); their targets attach to both words
BIGRAMS: dict[str, list[tuple[str, Fit]]] = {
    "fast food": [("fast_food", "exact"), ("dining", "nearest")],
    "video game": [("video_games", "exact"), ("games", "exact")],
}

_W_LEAF_LITERAL = 3.0
_W_LEAF_EXACT_SYN = 2.5
_W_LEAF_NEAREST_SYN = 1.5
_W_ANCESTOR_LITERAL = 1.0
_W_ANCESTOR_SYN = 0.5


def _singular(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 4 and t.endswith(("ches", "shes", "sses", "xes")):
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def _tokens(text: str) -> list[str]:
    words = _TOKEN.findall(text.lower().replace("_", " "))
    return [_singular(t) for t in words if t not in _STOP]


def _head(phrase: str) -> str | None:
    first = re.split(r"[;,:(]|\bnamely\b|\bincluding\b", phrase, flags=re.I)[0]
    toks = _tokens(first)
    return toks[-1] if toks else None


def _phrase_terms(phrase: str) -> dict[str, list[tuple[str, Fit]]]:
    """token -> synonym targets (bigram targets attach to both words of the bigram)."""
    toks = _tokens(phrase)
    terms: dict[str, list[tuple[str, Fit]]] = {t: list(SYNONYMS.get(t, [])) for t in toks}
    for a, b in zip(toks, toks[1:], strict=False):
        targets = BIGRAMS.get(f"{a} {b}")
        if targets:
            for w in (a, b):
                terms[w] = targets + terms[w]
    return terms


def _score_node(
    node: TaxonomyNode, terms: dict[str, list[tuple[str, Fit]]], head: str | None
) -> tuple[float, Fit] | None:
    leaf_tokens = set(_tokens(node.name)) | set(_tokens(node.slug))
    anc_slugs = set(node.path[:-1])
    anc_tokens = {t for seg in node.path[:-1] for t in _tokens(seg)} - leaf_tokens
    score = 0.0
    fits: set[str] = set()
    head_named = False
    for tok, syns in terms.items():
        if tok in leaf_tokens:
            score += _W_LEAF_LITERAL
            fits.add("partial")
            head_named |= tok == head
            continue
        leaf_syn = {f for slug, f in syns if slug == node.slug}
        if "exact" in leaf_syn:
            score += _W_LEAF_EXACT_SYN
            fits.add("partial")
            head_named |= tok == head
        elif leaf_syn:
            score += _W_LEAF_NEAREST_SYN
            fits.add("nearest")
        elif tok in anc_tokens:
            score += _W_ANCESTOR_LITERAL
        elif any(slug in anc_slugs for slug, _ in syns):
            score += _W_ANCESTOR_SYN
    if not fits:  # no phrase word names this node itself
        return None
    fit: Fit = "exact" if head_named else ("partial" if "partial" in fits else "nearest")
    return round(score, 2), fit


def map_goods_phrase(
    phrase: str, taxonomy: list[TaxonomyNode], max_n: int = MAX_MATCHES
) -> list[ProxyMatch]:
    """Up to `max_n` taxonomy nodes for a goods phrase, best first (score, then fit, then the
    deeper node, then tag_id). A node qualifies only if a phrase word names it (literally or via
    the synonym table); [] when nothing does."""
    if not phrase or not phrase.strip() or not taxonomy or max_n <= 0:
        return []
    terms = _phrase_terms(phrase)
    if not terms:
        return []
    head = _head(phrase)
    scored: list[ProxyMatch] = []
    for node in taxonomy:
        r = _score_node(node, terms, head)
        if r is not None:
            scored.append(ProxyMatch(node=node, fit=r[1], score=r[0]))
    scored.sort(key=lambda m: (-m.score, FIT_ORDER[m.fit], -m.node.depth, m.node.tag_id))
    return scored[:max_n]


def best_fit(fits: list[str]) -> Fit | None:
    """The strongest fit label in a list ("exact" > "partial" > "nearest")."""
    valid = [f for f in fits if f in FIT_ORDER]
    return min(valid, key=lambda f: FIT_ORDER[f]) if valid else None  # type: ignore[return-value]
