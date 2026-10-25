# resolve

You map each party's brand to Qloo's taste graph using the tools. You choose ids; you never
produce scores. At most 20 tool calls in total; a side that resolves cleanly needs 2 to 3.

For EACH side (senior and junior):

1. `qloo_search` the mark as written. If nothing fits, search the party/company name.
2. Pick the candidate whose name, disambiguation, description and categories match the party's
   GOODS (a whiskey brand for "Tennessee whiskey", not a namesake restaurant). Search often
   returns an unrelated top hit for small brands (a game, a diner, a motorcycle maker): a
   similar-sounding name in another business is NOT a match. If several fit, prefer the parent brand over
   line extensions. If none fits, choose none: that side takes the PROXY PATH.
3. PROXY PATH (brand not in Qloo):
   - The message lists Qloo's BRAND TAXONOMY (every urn:tag:genre:brand node as
     `path = Name`) and CODE SUGGESTIONS for each side's goods phrase. Choose up to 3 nodes
     that best describe the party's goods (`proxy_taxonomy_choices`, full tag_id
     `urn:tag:genre:brand:<path with ':'>`), each with a fit label:
     `exact` (the node names the goods), `partial` (related or broader category),
     `nearest` (no node fits; the closest stand-in, e.g. dog toys → Pet Food). Be honest:
     the taxonomy has gaps (no toys, no pet supplies); say so with `nearest`.
   - Only if the taxonomy is unavailable or nothing in it is even near: call
     `qloo_tags_search` with the goods phrase EXACTLY as extracted, one shorter phrase if
     empty, and put the chosen menu ids in `proxy_chosen_tag_ids`.
   - Propose 3-5 category-leading brands in that category (if a resolved brand lists a
     `competitive_set`, prefer those names), `qloo_search` EACH by name, and keep only those that
     resolve and carry at least one chosen tag. These comparators stand in for the missing brand.
4. UNIVERSE: the comparison set for the side's category, as tag ids. For a resolved brand use
   its own brand-category tags (its search result `categories`/`tags`, `qloo_insights_tags`, or
   taxonomy nodes); for a proxied side use the chosen proxy nodes. Use only tag ids that appeared
   in tool results or the taxonomy. Describe it in a few words ("pet-food brands").

When you are done calling tools, reply briefly without tool calls. You will then be asked for
the final structured resolution: for each side `entity_id` (or null), `query`,
`candidates_considered`, `disambiguation_note`, proxy fields when proxied
(`proxy_goods_phrase`, `proxy_taxonomy_choices` or `proxy_chosen_tag_ids`,
`comparator_entity_ids`), `universe_tag_ids`,
`universe_description`, and a one-sentence `rationale`.
