# route

Decide which taste-graph analyses Tea Rose should run for this dispute.

Analyses:

- `overlap`: do the two brands share purchasers (relatedness of goods, channels and
  purchasers)? Relevant to every likelihood-of-confusion claim.
- `bridging`: does the senior brand's audience already lean toward the junior's product
  category (likelihood the senior would expand / "bridge the gap")?
- `fame`: how broad is the senior brand's recognition across age/gender groups and the
  country? Required when dilution is pleaded; also useful for the strength-of-mark factor.
- `zone`: where geographically is each brand's audience concentrated? Relevant to
  common-law priority and zone-of-natural-expansion disputes.

Return `analyses` (the ones to run) and `rationale`: one sentence per analysis (all four)
saying why it is or is not run, tied to the pleaded claims. Code adds mandatory analyses
afterwards, so do not worry about omissions; focus on a clear rationale.
