"""Qloo's brand-category taxonomy (urn:tag:genre:brand) and a deterministic goods mapper.

Live spike facts: the taxonomy is a tree of ~177 nodes in 27 top families, depth 1-4
(e.g. urn:tag:genre:brand:wine_and_spirits:spirits:whiskey:bourbon). /v2/tags lists nothing
without filter.query, matches the query against node NAMES, and returns < 50 nodes for any single
letter, so 26 letter queries harvest the whole tree. Free-text goods phrases mostly miss
("dog toy", "handbags" -> 0), and there is no pet-supplies or toy node at all: a dog-toy maker's
nearest node is food_and_beverage:pet_food, which must be reported as an approximation.

`map_goods_phrase` scores nodes by token overlap with the node name and path plus a small
synonym table and labels each match:
- "exact":   the phrase's head noun (last word before the first comma/preposition) names the
             node, literally or through an equivalent synonym (bourbon -> whiskey);
- "partial": some phrase word names the node, or a related/broader synonym links them
             (toys -> games, search advertising -> software);
- "nearest": only a stand-in synonym links them ("squeaky dog chew toy" -> Pet Food):
             no exact match exists in Qloo's brand taxonomy.
Synonym targets are full paths that exist in the live tree (leaf slugs repeat across families).
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
     "from", "namely", "including", "other", "related", "use", "goods", "services", "service",
     "product", "products", "featuring", "being", "such", "brand", "brands", "line", "type",
     "kind", "style"}
)  # fmt: skip
_TOKEN = re.compile(r"[a-z0-9]+")
_HEAD_CUT = re.compile(
    r"[;,:(]|\b(?:namely|including|from|for|with|of|by|made|sold|under)\b", flags=re.I
)

# Synonym targets are FULL paths below urn:tag:genre:brand (leaf slugs repeat across the tree:
# "fashion" is a family, retail:fashion and entertainment:media:fashion). Strength:
#   exact   - an equivalent or narrower term for that node (bourbon -> whiskey);
#   partial - related or broader, a fair category but not the goods themselves (toys -> games);
#   nearest - a stand-in because the taxonomy has no node for the goods (dog toy -> pet food).
# All paths below exist in the live tree harvested during the spike (177 nodes).
_WS = "wine_and_spirits"
_SP = "wine_and_spirits:spirits"
_FB = "food_and_beverage"
_DR = "food_and_beverage:drinks"
_FD = "food_and_beverage:food"
_FA = "fashion"
_AC = "fashion:accessories"
_FW = "fashion:footwear"
_EL = "electronics"
_EN = "entertainment"
PET = f"{_FB}:pet_food"

SYNONYMS: dict[str, list[tuple[str, Fit]]] = {
    # wine & spirits
    "whisky": [(f"{_SP}:whiskey", "exact")],
    "bourbon": [(f"{_SP}:whiskey:bourbon", "exact"), (f"{_SP}:whiskey", "exact")],
    "rye": [(f"{_SP}:whiskey:rye", "exact"), (f"{_SP}:whiskey", "exact")],
    "scotch": [(f"{_SP}:whiskey:scotch", "exact"), (f"{_SP}:whiskey", "exact")],
    "liquor": [(_SP, "exact")],
    "vodka": [(f"{_SP}:vodka", "exact")],
    "tequila": [(f"{_SP}:tequila", "exact")],
    "mezcal": [(f"{_SP}:tequila", "partial")],
    "gin": [(f"{_SP}:gin", "exact")],
    "rum": [(f"{_SP}:rum", "exact")],
    "liqueur": [(f"{_SP}:liqueur", "exact")],
    "ale": [(f"{_WS}:beer", "exact")],
    "lager": [(f"{_WS}:beer", "exact")],
    "brewery": [(f"{_WS}:beer", "exact")],
    "cider": [(f"{_WS}:beer:cider", "exact")],
    "champagne": [(f"{_WS}:wine:sparkling", "exact"), (f"{_WS}:wine", "exact")],
    "prosecco": [(f"{_WS}:wine:sparkling", "exact"), (f"{_WS}:wine", "exact")],
    "sparkling": [(f"{_WS}:wine:sparkling", "partial")],
    "winery": [(f"{_WS}:wine", "exact")],
    # drinks
    "coffee": [(f"{_DR}:coffee_and_tea", "exact")],
    "espresso": [(f"{_DR}:coffee_and_tea", "exact")],
    "tea": [(f"{_DR}:coffee_and_tea", "exact")],
    "coffeehouse": [("dining", "exact"), (f"{_DR}:coffee_and_tea", "partial")],
    "cafe": [("dining", "exact"), (f"{_DR}:coffee_and_tea", "partial")],
    "water": [(f"{_DR}:non_carbonated", "exact")],
    "artesian": [(f"{_DR}:non_carbonated", "exact")],
    "mineral": [(f"{_DR}:non_carbonated", "partial")],
    "bottled": [(_DR, "partial")],
    "juice": [(f"{_DR}:juice", "exact")],
    "soda": [(f"{_DR}:carbonated", "exact")],
    "cola": [(f"{_DR}:carbonated", "exact")],
    "beverage": [(_DR, "partial")],
    "drink": [(_DR, "partial")],
    # food
    "candy": [(f"{_FD}:candy_and_confectionery", "exact")],
    "chocolate": [(f"{_FD}:candy_and_confectionery", "exact")],
    "confectionery": [(f"{_FD}:candy_and_confectionery", "exact")],
    "snack": [(f"{_FD}:packaged:snacks", "exact")],
    "chip": [(f"{_FD}:packaged:snacks", "partial")],
    "cracker": [(f"{_FD}:packaged:snacks", "partial")],
    "cheese": [(f"{_FD}:dairy_and_substitutes", "exact")],
    "milk": [(f"{_FD}:dairy_and_substitutes", "exact")],
    "yogurt": [(f"{_FD}:dairy_and_substitutes", "exact")],
    "ham": [(f"{_FD}:meat_seafood_and_substitutes", "exact")],
    "meat": [(f"{_FD}:meat_seafood_and_substitutes", "exact")],
    "sausage": [(f"{_FD}:meat_seafood_and_substitutes", "exact")],
    "seafood": [(f"{_FD}:meat_seafood_and_substitutes", "exact")],
    "cereal": [(f"{_FD}:breakfast", "exact")],
    "bread": [(f"{_FD}:bakery", "exact")],
    "cookie": [(f"{_FD}:bakery", "partial"), (f"{_FD}:packaged:snacks", "partial")],
    # pets: Qloo has pet food only, no pet supplies and no toys
    "dog": [(PET, "nearest")],
    "puppy": [(PET, "nearest")],
    "cat": [(PET, "nearest")],
    "kitten": [(PET, "nearest")],
    "pet": [(PET, "nearest")],
    "treat": [(PET, "nearest")],
    "kibble": [(PET, "exact")],
    # dining
    "restaurant": [("dining", "exact")],
    "burger": [("dining", "exact")],
    "hamburger": [("dining", "exact")],
    "pizza": [("dining", "exact")],
    "pizzeria": [("dining", "exact")],
    "diner": [("dining", "exact")],
    # fashion
    "apparel": [(_FA, "exact"), (f"{_FA}:casual", "partial")],
    "clothing": [(_FA, "exact"), (f"{_FA}:casual", "partial")],
    "garment": [(_FA, "exact"), (f"{_FA}:casual", "partial")],
    "shirt": [(f"{_FA}:casual", "exact")],
    "tshirt": [(f"{_FA}:casual", "exact")],
    "sweatshirt": [(f"{_FA}:casual", "exact")],
    "hoodie": [(f"{_FA}:casual", "exact")],
    "luxury": [(f"{_FA}:haute_couture", "partial")],
    "couture": [(f"{_FA}:haute_couture", "exact")],
    "designer": [(f"{_FA}:haute_couture", "partial")],
    "handbag": [(f"{_AC}:bags_and_leather", "exact")],
    "purse": [(f"{_AC}:bags_and_leather", "exact")],
    "bag": [(f"{_AC}:bags_and_leather", "exact")],
    "tote": [(f"{_AC}:bags_and_leather", "exact")],
    "backpack": [(f"{_AC}:bags_and_leather", "exact")],
    "luggage": [(f"{_AC}:bags_and_leather", "partial")],
    "wallet": [(f"{_AC}:bags_and_leather", "exact")],
    "watch": [(f"{_AC}:watch", "exact")],
    "wristwatch": [(f"{_AC}:watch", "exact")],
    "timepiece": [(f"{_AC}:watch", "exact")],
    "jewelry": [(f"{_AC}:jewelry", "exact")],
    "jewellery": [(f"{_AC}:jewelry", "exact")],
    "ring": [(f"{_AC}:jewelry", "exact")],
    "necklace": [(f"{_AC}:jewelry", "exact")],
    "bracelet": [(f"{_AC}:jewelry", "exact")],
    "earring": [(f"{_AC}:jewelry", "exact")],
    "diamond": [(f"{_AC}:jewelry", "exact")],
    "sunglass": [(f"{_AC}:eyewear", "exact")],
    "eyeglass": [(f"{_AC}:eyewear", "exact")],
    "shoe": [(_FW, "exact")],
    "boot": [(_FW, "exact")],
    "sandal": [(f"{_FW}:sandals", "exact"), (_FW, "exact")],
    "sneaker": [(f"{_FW}:sneakers", "exact"), (_FW, "exact")],
    "trainer": [(f"{_FW}:sneakers", "exact"), (_FW, "exact")],
    "skateboarding": [(f"{_FW}:sneaker:skateboarding", "partial")],
    "activewear": [(f"{_FA}:athletic", "exact")],
    "sportswear": [(f"{_FA}:athletic", "exact")],
    "athleisure": [(f"{_FA}:athletic", "exact")],
    "lingerie": [(f"{_FA}:lingerie_and_sleepwear", "exact")],
    "underwear": [(f"{_FA}:lingerie_and_sleepwear", "exact")],
    "pajama": [(f"{_FA}:lingerie_and_sleepwear", "exact")],
    "denim": [(f"{_FA}:jeans", "exact")],
    "bikini": [(f"{_FA}:swimwear", "exact")],
    "suit": [(f"{_FA}:formalwear", "exact")],
    "tuxedo": [(f"{_FA}:formalwear", "exact")],
    # health & beauty
    "beauty": [("health_and_beauty", "exact")],
    "cosmetic": [("health_and_beauty", "exact")],
    "makeup": [("health_and_beauty", "exact")],
    "fragrance": [("health_and_beauty", "exact")],
    "perfume": [("health_and_beauty", "exact")],
    "cologne": [("health_and_beauty", "exact")],
    "lotion": [("health_and_beauty:skincare", "exact")],
    "moisturizer": [("health_and_beauty:skincare", "exact")],
    "shampoo": [("health_and_beauty:hair_care", "exact")],
    "toothpaste": [("health_and_beauty:oral_care", "exact")],
    # retail and online
    "grocery": [("retail", "exact")],
    "supermarket": [("retail", "exact")],
    "store": [("retail", "partial")],
    "shop": [("retail", "partial")],
    "marketplace": [("retail", "partial"), ("website", "partial")],
    "resale": [("retail", "exact")],
    "ecommerce": [("retail", "partial"), ("website", "partial")],
    "website": [("website", "exact")],
    "app": [("mobile_app", "exact")],
    "advertising": [("software", "partial")],
    # electronics
    "audio": [(f"{_EL}:home_theater", "exact")],
    "speaker": [(f"{_EL}:home_theater", "exact")],
    "radio": [(f"{_EL}:home_theater", "exact")],
    "amplifier": [(f"{_EL}:home_theater", "exact")],
    "stereo": [(f"{_EL}:home_theater", "exact")],
    "television": [(f"{_EL}:home_theater", "partial")],
    "headphone": [(f"{_EL}:headphones", "exact")],
    "earbud": [(f"{_EL}:headphones", "exact")],
    "guitar": [(f"{_EL}:music_instruments", "exact")],
    "piano": [(f"{_EL}:music_instruments", "exact")],
    "instrument": [(f"{_EL}:music_instruments", "partial")],
    "phone": [(f"{_EL}:phones_and_tablets", "exact")],
    "smartphone": [(f"{_EL}:phones_and_tablets", "exact")],
    "tablet": [(f"{_EL}:phones_and_tablets", "exact")],
    "computer": [(f"{_EL}:computers_and_laptops", "exact")],
    "laptop": [(f"{_EL}:computers_and_laptops", "exact")],
    "camera": [(f"{_EL}:camera_and_video", "exact")],
    "appliance": [(f"{_EL}:appliances", "exact")],
    # entertainment, education, software
    "book": [(f"{_EN}:publisher", "exact")],
    "publishing": [(f"{_EN}:publisher", "exact")],
    "magazine": [(f"{_EN}:publisher", "exact"), (f"{_EN}:media", "partial")],
    "comic": [(f"{_EN}:publisher", "exact")],
    "recording": [(f"{_EN}:record_label", "partial")],
    "film": [(f"{_EN}:production_company", "exact")],
    "movie": [(f"{_EN}:production_company", "exact")],
    "educational": [("academic", "exact")],
    "education": [("academic", "exact")],
    "tutoring": [("academic", "exact")],
    "university": [("academic", "exact")],
    "toy": [("games", "partial")],
    "doll": [("games", "partial")],
    "puzzle": [("games", "partial")],
    # automotive, travel, sport
    "car": [("automotive:car_and_suv", "exact"), ("automotive", "exact")],
    "vehicle": [("automotive", "exact")],
    "truck": [("automotive:commercial", "partial"), ("automotive", "exact")],
    "motorcycle": [("automotive:motorcycle", "exact")],
    "tire": [("automotive", "partial")],
    "hotel": [("travel:hotel", "exact")],
    "resort": [("travel:hotel", "exact")],
    "airline": [("travel:airline", "exact")],
    "cruise": [("travel:cruise", "exact")],
    "team": [("sports_organization", "exact")],
    "league": [("sports_organization:league_tournament", "exact")],
    "bank": [("financial_services", "exact")],
    "banking": [("financial_services", "exact")],
    "insurance": [("financial_services", "exact")],
}
# two-word phrases (singularised tokens); their targets attach to both words
BIGRAMS: dict[str, list[tuple[str, Fit]]] = {
    "fast food": [("dining", "exact")],
    "chew toy": [(PET, "nearest")],
    "dog toy": [(PET, "nearest")],
    "pet toy": [(PET, "nearest")],
    "cat toy": [(PET, "nearest")],
    "pet supply": [(PET, "nearest")],
    "pet food": [(PET, "exact")],
    "dog food": [(PET, "exact")],
    "cat food": [(PET, "exact")],
    "leather good": [(f"{_AC}:bags_and_leather", "exact")],
    "t shirt": [(f"{_FA}:casual", "exact")],
    "bottled water": [(f"{_DR}:non_carbonated", "exact")],
    "mineral water": [(f"{_DR}:non_carbonated", "exact")],
    "energy drink": [(f"{_DR}:energy_drink", "exact")],
    "sport drink": [(f"{_DR}:sport_drinks", "exact")],
    "video game": [("games", "exact"), (f"{_EN}:video_game_developer", "partial")],
    "board game": [("games", "exact")],
    "toy vehicle": [("games", "partial")],
    "audio system": [(f"{_EL}:home_theater", "exact")],
    "home theater": [(f"{_EL}:home_theater", "exact")],
    "musical instrument": [(f"{_EL}:music_instruments", "exact")],
    "music recording": [(f"{_EN}:record_label", "exact")],
    "record label": [(f"{_EN}:record_label", "exact")],
    "test preparation": [("academic", "exact")],
    "language learning": [("academic", "exact")],
    "educational material": [("academic", "exact")],
    "preparation material": [("academic", "exact")],
    "search advertising": [("software", "partial")],
    "keyword advertising": [("software", "partial")],
    "online marketplace": [("website", "exact"), ("retail", "partial")],
    "online retail": [("retail", "exact"), ("website", "partial")],
    "luxury resale": [("retail:fashion", "exact"), ("retail", "partial")],
    "discount fashion": [("retail:fashion", "exact")],
    "credit card": [("financial_services:credit_card", "exact")],
    "car rental": [("travel:car_rental", "exact")],
}

_W_LEAF_LITERAL = 3.0
_W_LEAF_SYN: dict[str, float] = {"exact": 2.5, "partial": 2.0, "nearest": 1.5}
_W_ANCESTOR_LITERAL = 1.0
_W_ANCESTOR_SYN = 0.5
_HEAD_BONUS = 1.0  # the node names the head noun
_UNMATCHED_ANCESTOR_PENALTY = 0.1  # prefers "fashion" over "entertainment:media:fashion"


def _singular(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 4 and t.endswith(("ches", "shes", "sses", "xes")):
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def _tokens(text: str) -> list[str]:
    words = _TOKEN.findall(text.lower().replace("_", " "))
    return [_singular(t) for t in words if len(t) > 1 and t not in _STOP]


def _head(phrase: str) -> str | None:
    toks = _tokens(_HEAD_CUT.split(phrase)[0])
    return toks[-1] if toks else None


def _phrase_terms(phrase: str) -> dict[str, list[tuple[str, Fit]]]:
    """token -> synonym targets (a bigram's targets replace those of both its words)."""
    toks = _tokens(phrase)
    terms: dict[str, list[tuple[str, Fit]]] = {t: list(SYNONYMS.get(t, [])) for t in toks}
    for a, b in zip(toks, toks[1:], strict=False):
        targets = BIGRAMS.get(f"{a} {b}")
        if targets:  # the two-word meaning replaces the single-word synonyms
            for w in (a, b):
                terms[w] = list(targets)
    return terms


def _strongest(fits: set[str]) -> str:
    return min(fits, key=lambda f: FIT_ORDER[f])


def _score_node(
    node: TaxonomyNode, terms: dict[str, list[tuple[str, Fit]]], head: str | None
) -> tuple[float, Fit] | None:
    path = ":".join(node.path)
    ancestors = [":".join(node.path[:i]) for i in range(1, node.depth)]
    leaf_tokens = set(_tokens(node.name)) | set(_tokens(node.slug))
    anc_tokens = {a: set(_tokens(node.path[i])) for i, a in enumerate(ancestors)}
    matched_anc: set[str] = set()
    score = 0.0
    fits: set[str] = set()
    head_named = False
    for tok, syns in terms.items():
        if tok in leaf_tokens:
            score += _W_LEAF_LITERAL
            fits.add("partial")
            head_named |= tok == head
            continue
        leaf_syn = {f for target, f in syns if target == path}
        if leaf_syn:
            strength = _strongest(leaf_syn)
            score += _W_LEAF_SYN[strength]
            fits.add("partial" if strength == "exact" else strength)
            head_named |= strength == "exact" and tok == head
            continue
        lit = [a for a in ancestors if tok in anc_tokens[a]]
        syn = [a for a in ancestors if any(target == a for target, _ in syns)]
        if lit:
            score += _W_ANCESTOR_LITERAL
        elif syn:
            score += _W_ANCESTOR_SYN
        matched_anc.update(lit + syn)
    if not fits:  # no phrase word names this node itself
        return None
    score -= _UNMATCHED_ANCESTOR_PENALTY * (len(ancestors) - len(matched_anc))
    if head_named:
        score += _HEAD_BONUS
    fit: Fit = "exact" if head_named else _strongest(fits)  # type: ignore[assignment]
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
