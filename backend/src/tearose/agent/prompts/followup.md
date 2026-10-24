# followup

Counsel asked a follow-up question about a finished Tea Rose analysis. Decide the smallest
re-run that answers it and return a `FollowupPlan`:

- `re_resolve_junior_goods`: the junior's goods were characterised wrongly or too narrowly;
  set `junior_goods_phrase` to the phrase to use (verbatim from counsel or the document).
- `add_comparator`: counsel names other brands that should stand in for, or be compared with,
  a party; list them in `comparator_names`.
- `change_universe`: the comparison category should be different or broader/narrower.
- `recompute_only`: the data is fine; the question is about interpretation or wording.

`instruction`: one or two imperative sentences for the downstream steps (resolution, fetching,
interpretation, memo). `rationale`: one sentence. Do not answer the question yourself.
