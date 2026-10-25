"""Code rule for proxy comparators, shared by the agent's resolve node and the back-test.

A proxied side (brand not in Qloo) is represented by comparator BRANDS. The rule: brands
returned by /v2/insights filter.type=urn:entity:brand seeded with the OTHER side (its resolved
entity, or its comparators when it is proxied too) and filtered to the proxy tag(s), page 1,
take 50; an empty result with several tags is retried once with the broadest tag. Pick the top
3 by POPULARITY (ties by rank), excluding the seeds and the other side's own brand (by entity id
and by normalised name, so a duplicate entity of the opponent can never stand in for it). Not
by rank, on purpose: the brands that
rank highest for the senior would make senior->junior rank 1-3 by construction; popularity is a
property of the brand, not of the other side's audience ("category leaders").

The product's resolve node uses the same query with n=10 to build the agent's SHORTLIST
(same seeds, tags and exclusions, ordered by popularity); the agent then picks 3 from it, and
this rule's top 3 are the fallback when the agent returns fewer than 2 valid picks. The
back-test's rule resolver uses the rule directly.

No model and no network here: the caller passes the fetch function (ToolContext or Recorder).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable

from tearose.qloo.models import Entity
from tearose.qloo.names import normalize_name

COMPARATOR_COUNT = 3
COMPARATOR_RULE = (
    "top 3 by popularity (ties by rank) among brands seeded by the other side's entity and "
    "filtered to the proxy tags, never the other side's own brand; not by rank, to avoid a "
    "built-in senior->junior overlap"
)

FetchPage = Callable[[list[str], list[str]], Awaitable[list[Entity]]]


def broadest_tag(tag_ids: list[str] | tuple[str, ...]) -> str:
    """Fewest path segments wins (same rule as the agent's ToolContext)."""
    return min(tag_ids, key=lambda t: (t.count(":"), len(t)))


def top_by_popularity(
    batch: Iterable[Entity],
    exclude: Iterable[str] = (),
    n: int = COMPARATOR_COUNT,
    exclude_names: Iterable[str] = (),
) -> list[Entity]:
    """Top `n` by popularity (missing popularity last), ties by response order; `exclude` ids,
    names equal to an `exclude_names` entry after normalisation, and duplicate ids are skipped."""
    skip = set(exclude)
    skip_names = {k for k in (normalize_name(x) for x in exclude_names if x) if k}
    pool: list[tuple[float, int, Entity]] = []
    for i, e in enumerate(batch):
        if e.entity_id in skip or (skip_names and normalize_name(e.name) in skip_names):
            continue
        skip.add(e.entity_id)
        pool.append((e.popularity if e.popularity is not None else -1.0, i, e))
    pool.sort(key=lambda t: (-t[0], t[1]))
    return [e for _, _, e in pool[:n]]


async def rule_comparators(
    fetch: FetchPage,
    seeds: list[str],
    proxy_tags: list[str],
    exclude: Iterable[str] = (),
    n: int = COMPARATOR_COUNT,
    exclude_names: Iterable[str] = (),
) -> tuple[list[Entity], list[str]]:
    """(comparators, notes). `fetch(seeds, tags)` returns page 1 (take 50) of brand insights.
    Seeds and `exclude` ids are always excluded from the pick, as is any brand whose normalised
    name equals one of `exclude_names` (the other side's name); empty seeds or tags give
    ([], note)."""
    if not seeds:
        return [], ["comparators: nothing resolved on the other side to seed with."]
    if not proxy_tags:
        return [], ["comparators: no proxy tags to filter with."]
    notes: list[str] = []
    batch = list(await fetch(seeds, proxy_tags))
    if not batch and len(proxy_tags) > 1:
        broad = broadest_tag(proxy_tags)
        notes.append(f"comparators: empty with {len(proxy_tags)} tags; retried with {broad}.")
        batch = list(await fetch(seeds, [broad]))
    return top_by_popularity(batch, [*seeds, *exclude], n, exclude_names), notes
