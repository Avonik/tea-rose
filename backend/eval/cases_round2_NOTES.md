# Round 2 candidates: notes

**Pre-registration reminder:** the labels in `cases_candidates_round2.csv` were written on 2026-10-25, before any Qloo score was computed for these brand pairs.

## Counts

- Cases considered: 50.
- Kept: 28. Relatedness labels: 17 favors_plaintiff, 7 favors_defendant, 3 neutral, 1 not_discussed. Channels labels: 16 favors_plaintiff, 5 favors_defendant, 7 not_discussed. fame_found: 3 yes, 2 no, 23 not_at_issue. Confidence: 20 high, 8 medium.
- Rows with at least one factor favoring the defendant: 9. Those are Caterpillar, AM General, Checkpoint, Freedom Card, Hershey, NYSE, Therma-Scan, Surfvivor and Sullivan; AutoZone is neutral and leans the same way. This is one short of the target of 10. Three of the nine have a senior party that is not a known brand: Freedom Card, Therma-Scan and Surfvivor. They were kept for the variation, and the notes column flags them.
- Dropped: 22.
  - Read, but the court does not discuss the factors (10): Kellogg v. Exxon (acquiescence only), Gibson v. PRS, PRL v. USPA (2d Cir. 2008), USPA v. PRL (2d Cir. 2015, contempt), Nabisco v. Warner-Lambert, RiseandShine v. PepsiCo, Fox v. Marvel, LV v. Warner Bros. (Rogers), and Gibson v. Armadillo (evidentiary ruling). Lions Gate v. TD Ameritrade was also dropped because it is a copyright-preemption motion to dismiss with no factor analysis.
  - Read, but one party is not a brand, or the label would be ambiguous (2): Westchester Media (POLO magazine) v. PRL, and Brennan's v. Brennan's Restaurant (single restaurants; proximity is split between market and geography).
  - No usable opinion retrieved (10): Kind v. Clif Bar, UMG v. Mattel (TTAB, Motown Metal), Louis Vuitton v. Hyundai, Hansen v. Cytosport, Yeti v. RTIC (GovInfo has discovery orders only), Under Armour v. Body Armor (discovery order only), Juicy Couture v. L'Oreal, Gap v. G Adventures, Express v. Forever 21, and Victoria's Secret v. Sexy Hair Concepts.

## Method notes

- The rules are the same as in `README.md`. Each label comes only from the opinion text that was read. `opinion_url` is the exact file that was read: a CAP JSON, a GovInfo PDF, or a CourtListener RECAP PDF.
- Quotes were taken programmatically from the downloaded text, with whitespace normalized and PDF line numbers removed.
- Two rows have no automatic quote check. AM General (Doc. 218) and Easy Spirit (Doc. 185) are scanned PDFs with no text layer. Their pages were read as images and the quotes were transcribed by hand, so the quote-check script cannot verify them.
- Several brand pairs are uneven: GoTo.com is defunct, and Variety Stores (Roses), Art Van and Georgi are regional or low-tier. Checkpoint v. Check Point is business-to-business. The notes column says which side may be thin in Qloo.
