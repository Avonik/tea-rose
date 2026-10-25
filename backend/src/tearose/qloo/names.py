"""Conservative brand-name matching for /search results.

/search ranks by its own relevance and happily returns an unrelated entity as the top hit for a
small brand ("Triumph Learning" -> a motorcycle maker). So we never take "the first result":
a candidate counts only if its name matches the query after normalisation (exact), or passes a
strict similarity rule (fuzzy). Otherwise the side is a MISS and takes the proxy path.

Rules, in order (the rule string is recorded with every resolution):
- "exact": normalised names are equal, or equal once spaces are removed ("bark box" = "barkbox").
- "fuzzy:<ratio>": with two or more query tokens, every query token appears in the candidate
  and the candidate adds at most one extra token ("jack daniels" ~ "jack daniels
  distillery"), or the difflib ratio of the normalised names is >= FUZZY_MIN_RATIO. <ratio>
  is that difflib ratio, two decimals.
- "miss": nothing qualifies.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher

from tearose.qloo.models import Entity

FUZZY_MIN_RATIO = 0.9
MAX_EXTRA_TOKENS = 1
CORPORATE_SUFFIXES = frozenset(
    {"inc", "incorporated", "llc", "co", "corp", "corporation", "company", "ltd", "limited",
     "plc", "lp", "llp", "gmbh", "ag", "sa"}
)  # fmt: skip

_APOSTROPHES = re.compile(r"['’‘ʼ`´]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str) -> str:
    """casefold, strip accents, drop apostrophes, "&" -> "and", other punctuation -> space,
    trailing corporate words removed ("Jack Daniel's Properties, Inc." -> "jack daniels
    properties")."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = _APOSTROPHES.sub("", s).replace("&", " and ")
    tokens = _NON_ALNUM.sub(" ", s).split()
    while len(tokens) > 1 and tokens[-1] in CORPORATE_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def name_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def match_rule(query: str, candidate: str) -> str:
    """ "exact" | "fuzzy:<ratio>" | "miss" for one query/candidate pair."""
    q, c = normalize_name(query), normalize_name(candidate)
    if not q or not c:
        return "miss"
    if q == c or q.replace(" ", "") == c.replace(" ", ""):
        return "exact"
    ratio = SequenceMatcher(None, q, c).ratio()
    qt, ct = q.split(), c.split()
    # One-word queries never pass by subset: 'Viti' must not match 'Fabrizio Viti'.
    subset = len(qt) >= 2 and set(qt) <= set(ct) and len(ct) - len(qt) <= MAX_EXTRA_TOKENS
    if subset or ratio >= FUZZY_MIN_RATIO:
        return f"fuzzy:{ratio:.2f}"
    return "miss"


def _rank(rule: str) -> tuple[int, float]:
    if rule == "exact":
        return (0, 0.0)
    if rule.startswith("fuzzy:"):
        return (1, -float(rule.split(":", 1)[1]))
    return (2, 0.0)


def pick_by_name(
    queries: str | Iterable[str], results: list[Entity], avoid_ids: Iterable[str] = ()
) -> tuple[Entity | None, str]:
    """Best candidate across one or more query strings (a mark and the company name, say).

    Exact beats fuzzy; among fuzzy, the higher ratio wins; ties keep the API order. Entities in
    `avoid_ids` are skipped. Returns (None, "miss") when nothing qualifies - never the first hit.
    """
    qs = [queries] if isinstance(queries, str) else [q for q in queries if q and q.strip()]
    avoid = set(avoid_ids)
    best: tuple[tuple[int, float], int, Entity, str] | None = None
    for idx, e in enumerate(results):
        if e.entity_id in avoid:
            continue
        for q in qs:
            rule = match_rule(q, e.name)
            if rule == "miss":
                continue
            key = (_rank(rule), idx, e, rule)
            if best is None or key[:2] < best[:2]:
                best = key
    if best is None:
        return None, "miss"
    return best[2], best[3]
