# memo

Write a short evidence memo for litigation counsel from the material provided. Neutral: the
same memo must be usable by either side. Plain, precise lawyer prose; markdown allowed.

Return:

- `headline`: ONE sentence stating the main finding with its key number (rank/percentile as
  given), no hedging adjectives.
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
the findings say so. Brand names may be replaced by "Brand A (senior)" / "Brand B (junior)";
use them as given.
