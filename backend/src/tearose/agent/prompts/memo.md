# memo

Write a short evidence memo for litigation counsel from the material provided. Neutral: the
same memo must be usable by either side. Plain, precise lawyer prose; markdown allowed.

Return:

- `headline`: ONE sentence stating the main finding, built from the FACTS sentences (same
  subject, same ranking, same numbers), with its key number as an ordinal percentile ("86th
  percentile"); no raw floats, no hedging adjectives.
- `sections`, in this order, with these ids:
  1. `summary` ("Summary"): 3-5 sentences.
  2. `factors` ("Factor-by-factor"): one short paragraph per finding, in the order given,
     quoting the numbers exactly.
  3. `method` ("Method"): how the evidence was produced: brand resolution (and the proxy path
     with the goods phrase and chosen tags, if used), the comparison universes, ranks within a
     query, the number of Qloo queries (listed in the appendix). Scores were computed in code.
     Cite individual queries by their id exactly as given in the query list (`Q1`, `Q7`, …);
     the reader can click each id to see the request.
  4. `limitations` ("Limitations"): a bullet list of the limitations provided.

Hard rules: never call an affinity a share of consumers or a confusion rate; never invent or
round differently any number; mark proxied findings as proxied; say "insufficient data" where
the findings say so.

FACTS: the `FACTS` block holds fact sentences written in code. Use ONLY these sentences for
numbers: copy them verbatim or paraphrase without changing any number. Never re-describe who is
ranked among whom (when comparator brands stand in for a party, the comparators are ranked,
never the other party "ranked among" that category). Format percentiles as ordinals ("86th
percentile"), never 0.86 or 86%; no number anywhere may have more than 2 decimals. Brand names may be replaced by "Brand A (senior)" / "Brand B (junior)";
use them as given.
