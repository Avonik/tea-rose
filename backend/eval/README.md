# Evaluation set: `cases_candidates.csv`

52 decided (or formally terminated) US trademark matters, 2000–2026. In each one, at least the senior mark is a consumer-facing brand, and in most both are. The set is used to check whether Qloo cultural-affinity overlap between the senior and junior brand (or their goods categories) tracks how courts labelled two confusion factors: **relatedness of goods** and **channels / purchasers**.

## How the labels were produced

1. **Case selection.** Started from the plan's 10 showcase cases plus the suggested list. Pre-2000 cases were dropped (Hormel v. Henson, Ferrari, Pizzeria Uno, Two Pesos), as were cases with no decided opinion (Lululemon v. Peloton, Apple v. Prepear, Chick-fil-A). Cases where neither party is a consumer brand were also dropped (Toyota v. Tabari). Well-known consumer-brand cases were added (Pom, Maker's Mark, Fortune Dynamic v. Victoria's Secret, Kate Spade, Jada v. Mattel, Bose, Palm Bay/Veuve Clicquot, Recot/Frito-Lay, and others).
2. **Existence check and text retrieval.** Each case was located by citation and its opinion text was downloaded from one of:
   - Caselaw Access Project static files (`static.case.law`, reporters through 2018)
   - CourtListener opinion PDFs (`storage.courtlistener.com/pdf/...`) and RECAP docket PDFs
   - GovInfo `USCOURTS` PDFs
   - TTABVUE (for Taco Tuesday)

   The `opinion_url` column is the exact file that was read.
3. **Reading.** For each opinion the labeller read the factor sections: sentences on relatedness or proximity, channels, purchasers, fame, and the disposition, plus their surrounding context. The **only** basis for a label is what that opinion says. Background knowledge about later history was not used to set labels. Later history appears in `notes` only when it came from a document that was actually read.
4. **Quote check.** `quote_relatedness` is copied verbatim from the opinion text. A script checked every quote against the downloaded text after normalising whitespace, curly quotes, dashes and PDF line numbers. All quotes matched except *Tiffany v. Costco*, which is a footnote split across a PDF page break; both halves were checked by hand. Some quotes are clauses of a longer sentence, which the notes say. Quotes are at most 300 characters.
5. **Cases not read.** Where no opinion could be retrieved (In-N-Out v. Smashburger, Nike v. StockX, Chanel v. WGACA), the factor labels and `fame_found` are `unread` and `confidence` is `low`. Any outcome given in those rows comes from secondary sources, and the notes say so.

## Column definitions

| column | meaning |
|---|---|
| `senior_mark` / `senior_goods` | Mark (and goods) of the party asserting trademark rights, i.e. the senior user. In declaratory-judgment cases this is the **defendant/counterclaimant**: Jack Daniel's in the VIP rows, Saturdays Surf in *Kate Spade*. |
| `junior_mark` / `junior_goods` | The accused use. |
| `claims` | `confusion` (§32/§43(a) infringement), `dilution` (§43(c)), `both`, or `other` (Taco Tuesday: genericness/abandonment). Only the claims addressed in this opinion are listed. |
| `factor_relatedness_of_goods` | Court's treatment of the relatedness / proximity / similarity-of-goods factor (Sleekcraft 2, Polaroid 3, DuPont 2, Pizzeria Uno 3, Frisch 2, digit 3). |
| `factor_channels_purchasers` | Court's treatment of the marketing-channel / trade-channel / purchaser-identity factor (Sleekcraft 5, DuPont 3–4 classes of customers, Pizzeria Uno 4–5, Frisch 5, digit 4). Polaroid has no separate channels factor, so 2d Cir. cases are usually `not_discussed` unless the proximity discussion explicitly addresses channels or customers. |
| factor values | `favors_plaintiff` = favors the **mark owner** (see above), `favors_defendant` = favors the accused user, `neutral` = discussed but weighed neither way or explicitly equivocal, `not_discussed` = the opinion does not analyse the factor, `unread`. When an appellate court upholds or recites the lower tribunal's factor finding, that finding is the label (noted in `notes`). When an appellate court reverses a factor finding without resolving it (e.g., *Recot*), the label shows the direction of the correction and confidence is `medium`. |
| `fame_found` | Dilution-level (TDRA/FTDA) fame decided or conceded in **this** opinion: `yes`, `no`, or `not_at_issue` (not decided here, assumed, or left to trial). Likelihood-of-confusion fame (DuPont factor 5, e.g. *Coach*, *Palm Bay*, *Bose*) is recorded in `notes`, not here. |
| `outcome_confusion` | Disposition in this opinion of the trademark claim(s) listed in `claims`, from the mark owner's perspective: `plaintiff`, `defendant`, `mixed` (split by mark or claim, or summary judgment denied so the issue goes to trial), `remanded` (vacated/reversed for further proceedings), `settled` (surrender/settlement), `unknown`. Preliminary-injunction rulings count as outcomes. |
| `confidence` | `high` = the factor discussion and disposition were read directly and the labels follow from explicit language. `medium` = the labels rest on recited lower-tribunal findings, jury-verdict review, a remand, or a factor set only partly discussed. `low` = the opinion was not read. |

Counts: 39 high, 10 medium, 3 low (49 rows high or medium). Relatedness labels: 23 favors_plaintiff, 6 favors_defendant, 20 not_discussed, 3 unread. Channels labels: 14 favors_plaintiff, 6 favors_defendant, 2 neutral, 27 not_discussed, 3 unread.

## Pre-registration rule

The labels in `cases_candidates.csv` are **frozen before any Qloo score is computed** for any of these brand pairs.

- Commit this file (and this README) in a commit that contains no Qloo output. Record that commit hash in the evaluation report.
- After that, label changes are allowed only to fix a documented transcription error, such as a quote that does not match the opinion or the wrong party marked as senior. Each change must cite the opinion passage and be made in a separate commit before any further scoring run. A label may **not** change because a Qloo score disagrees with it.
- Decide the analysis subset before scoring: rows with `confidence` in {high, medium} and a factor label in {favors_plaintiff, favors_defendant, neutral}. `not_discussed` and `unread` rows are reported but excluded from accuracy metrics.
- Brand-to-Qloo entity mapping (which Qloo entity stands for "Bad Spaniels", "VITI", "Saturdays Surf NYC", etc.) should also be fixed in a separate file before scores are pulled. Unmatched entities are reported as misses, not silently dropped.

## Known limitations

- **Opinions discuss factors unevenly.** About 40% of rows have `not_discussed` relatedness. Appellate opinions often decide a threshold issue instead: Rogers/expressive works (*Mattel v. MCA*, *Seuss*), nominative use (*Tiffany v. eBay*), functionality (*A&F v. American Eagle*), validity (*Louboutin*), a procedural issue (*adidas v. Thom Browne*, Rule 60), or a dilution-only question (*Levi's*, *Moseley*, *Charbucks 2013*).
- **Many cases turn on mark similarity, not relatedness.** In *Jack Wolfskin*, *Sazerac*, *Maker's Mark* and the 2025 Bad Spaniels remand, relatedness or channels favored the mark owner, but the outcome went the other way, or was carried, by similarity, parody, or strength. A Qloo overlap score that predicts the relatedness label well will **not** predict outcomes on its own.
- **Parody inverts factors.** In *Haute Diggity Dog*, *My Other Bag*, *Hilfiger* and *VIP (2025)*, courts treat strength and similarity as cutting against the mark owner. High cultural overlap in a parody case can be evidence for the parodist.
- **Label granularity.** "Slightly favors" and "weighs heavily" collapse into one label. Per-mark splits (*Gucci v. Guess*) are reduced to one label with a note.
- **Party asymmetry.** Several junior users are not well-known brands (Black Bear, VITI, Smack Apparel, Victor's Little Secret, Pur Beverages, BeckerTime, Vintage Brand, MOB). Qloo coverage for these will be thin. The mapping may have to fall back to the goods category.
- **Same dispute, several rows.** Bad Spaniels has 4 rows, Charbucks 2, Victoria's Secret 2. Deduplicate by dispute when computing accuracy, or report both ways.
- **Selection bias.** Published, well-known cases over-represent luxury fashion, beverages and parody. Survey data appears in only a minority of opinions.
- **Retrieval.** CourtListener's anonymous search API rate-limited after about 40 queries, and SDNY and C.D. Cal. dockets are not on GovInfo, so several 2023–2025 district rulings (Nike v. StockX, Chanel v. WGACA, In-N-Out v. Smashburger, Patagonia v. Anheuser-Busch) could not be read. TTAB precedential decisions (e.g., UMG v. Mattel "Motown Metal", Yankees "Baseball Evil Empire") were not added for the same reason.

## Harness

Code: `backend/src/tearose/eval/backtest/`. Four idempotent steps, run from `backend/`:

```
uv run python -m tearose.eval.backtest prepare   # cases_candidates.csv -> mapping.csv (no Qloo calls)
uv run python -m tearose.eval.backtest resolve   # mapping.csv -> resolved.json (/search, /v2/tags, insights tags)
uv run python -m tearose.eval.backtest score     # resolved.json -> scores.json (insights + scoring/score.py)
uv run python -m tearose.eval.backtest report    # -> results/backtest_<YYYYMMDD>_v2.md/.json (+ frontend backtest.json on live runs)
```

**Harness version.** `HARNESS_VERSION` in `tearose/eval/backtest/__init__.py` is **2**. Run 1 (2026-10-25, `results/backtest_20261025.md/.json`) used the pre-registered v1 rules and is kept unchanged as the record. Harness v2 writes `backtest_<date>_v2.*`; `resolved.json` and `scores.json` carry `harness_version`, and `score` / `report` refuse inputs from another version. The v2 rule changes are listed under "Deviations from pre-registration" below.

No language model is called anywhere in the harness. Every choice is a deterministic rule in code, so the Qloo signal is evaluated on its own.

**Pre-registration rule for the mapping.** `mapping.csv` is the pre-registered mapping table: one row per case with the Qloo search strings, goods phrases, the same-category baseline, the combined label and inclusion flags. It is generated by `prepare` and **committed before any Qloo score is computed** (before `resolve`/`score` run in live mode). After that commit it changes only to fix a documented transcription error, in its own commit and before any further scoring run, never because a score disagrees. `prepare` refuses to overwrite a differing `mapping.csv` without `--force`. Every later output records the `mapping.csv` sha256, and `score` refuses a `resolved.json` built from a different mapping.

**Accused-side consistency rule.** The junior query is the brand the accused goods were sold under (the seller brand), not the product name. So the Bad Spaniels rows search "VIP Products", the Charbucks rows "Black Bear Micro Roastery", *Vans v. MSCHF* "MSCHF". Where the accused use is a work by a performer rather than a branded product (*Mattel v. MCA*: the song "Barbie Girl"), the side is searched as that performer with a non-brand entity type ("Aqua", `junior_type` = `artist`).

**Rules fixed in code:**

- *Queries.* Generic cleaning of the mark text (strip parentheticals, keep the first `/` `;` `,` segment, drop trailing descriptor words, title-case all-caps names except vowel-less 2-4 letter acronyms such as MTM), plus a reviewed override table (`QUERY_OVERRIDES` in `prepare.py`, reason copied to `query_note`) for rows where the mark column describes the accused use or names a product line or design rather than a brand.
- *Entity types.* `senior_type` / `junior_type` hold the Qloo entity type short name (default `brand`; `TYPE_OVERRIDES` in `prepare.py`, reason in `query_note`). `resolve` searches each side with that type; `score` uses the target side's type as `filter.type` in each overlap direction (a proxied side is represented by comparator brands, so its direction stays `brand`).
- *Goods phrases.* They go verbatim to /v2/tags when a side is not found, so they must be short category phrases. Generic cleaning (`clean_goods`): strip parentheticals, keep the text before the first `;`, remove URLs, `$` prices and price ranges and quote marks (not in-word apostrophes), collapse whitespace. A reviewed `GOODS_OVERRIDES` table (reason in `goods_note`) fixes brand names, vocabulary (whisky -> whiskey) and phrases still longer than 6 words or containing a digit; `prepare` lists any such phrase under `goods_phrases_to_review`. Categories are computed on the final phrase.
- *same_category.* A keyword lexicon of 14 buckets (the 13 planned plus sports/fitness). Each goods phrase gets the bucket of its earliest matching keyword. `yes` only when both phrases land in the same known bucket.
- *Labels.* Code favors_defendant = 0, neutral = 1, favors_plaintiff = 2. When both factor labels are decided and disagree, the row is `mixed` and excluded. Otherwise the decided one is used.
- *Resolve.* /search (the side's entity type, default brand; take 10). Pick the first exact case-insensitive name match, else the first result. If both sides pick the same entity, the junior counts as not found. Not found leads to the proxy path: the goods phrase is mapped onto the brand taxonomy (`map_goods_phrase`), with free-text /v2/tags (one shortened retry) and `pick_category_tags` only as the last resort. Universe (v2) = the brand's **own** `urn:tag:genre:brand` tags from its /search result, most specific nodes only (an ancestor of another node is dropped, depth >= 2 preferred, up to 3; source `entity own tags`). Only for a brand without own brand-genre tags: its insights tags restricted to brand genres, top 5 (source `insights tags (fallback)`, the v1 rule), then goods-phrase tags.
- *Score.* Same paging as the agent's fetch node (take 50, up to 3 pages, stop when targets are found; an empty first page is retried with the broadest tag). Proxy comparators are the top 3 **by popularity** among the brands seeded by the other side and filtered to the proxy tags. They are not ranked by affinity rank, because that would make the senior->junior rank 1 to 3 by construction. Fame (senior only) uses demographics and a "United States" heatmap.
- *Censoring and affinity ratio (v2).* After paging, every target's affinity is looked up directly (`/v2/insights`, same seeds, `filter.tags` and `filter.type`, plus `filter.results.entities=<target>`; one call per target). A target not in the scanned list is **censored**: no rank and no rank percentile (v1 counted it as rank 151, percentile 0); on the proxy path one missing comparator censors the direction. The second Qloo signal, `affinity_ratio` = target affinity / affinity of the top-ranked brand of the same list (0..1, comparator mean on the proxy path), exists whenever the lookup succeeds. `symmetric_percentile` = mean of the available rank percentiles; `symmetric_affinity_ratio` = mean of the available ratios. A case counts as scored when either signal exists.
- *Report.* Both Qloo signals (symmetric rank percentile, symmetric affinity ratio) are reported side by side in every subset table; each signal's n counts the cases where it exists. The primary metric uses non-proxy scored cases. Secondary lines: with proxies, deduplicated by dispute (latest year), and each factor label alone. Bootstrap: 2000 resamples, fixed seed. A metric with n < 15 is labelled underpowered.

**Output locations.** Live runs write to `backend/eval/`. Fixture runs write to `backend/eval/_fixture/` by default (override with `--out`). Fixture results never update `frontend/src/content/backtest.json` unless you pass `--frontend`.

## Deviations from pre-registration

On **2026-10-25**, after run 1 (`results/backtest_20261025.md`, kept unchanged as the record of the pre-registered harness), three harness rules were changed (harness v2). Each fixes a measurement error that was visible without looking at the labels:

1. **Universe rule.** Pre-registered: a brand's category universe was its top-5 insights tags (`filter.tag.types=urn:tag:genre:brand`). Those tags describe what the brand's *audience* likes, not what the brand is (a sneaker brand came out as "Food & Beverage"). Now: the brand's own `urn:tag:genre:brand` tags from its /search result, most specific nodes only (ancestors dropped, depth >= 2 preferred, up to 3). The insights-tags rule remains only as the fallback for a brand without own brand-genre tags.
2. **Censored ranks.** Pre-registered: a target not found among the first 150 brands counted as rank 151, i.e. percentile 0. Now such a rank is reported as censored (no rank percentile), and the target's affinity is looked up directly (`filter.results.entities=<target>`, same seeds, filter and type). This gives a second signal, the affinity ratio = target affinity / affinity of the top-ranked brand (0..1), reported next to the rank percentile.
3. **Taxonomy synonym.** "test preparation" / "test-preparation" / "educational materials" / "educational" mapped to `academic` (universities); they now map to `entertainment:publisher` (partial).

Labels (`cases_candidates.csv`) and `mapping.csv` are unchanged (same mapping sha256; `QUERY_OVERRIDES` / `GOODS_OVERRIDES` untouched). Run 1 is kept as the record; the v2 numbers are post-hoc and should be read as such. The v2 report repeats this section.
