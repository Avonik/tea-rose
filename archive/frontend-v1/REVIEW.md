# Front-end review (fresh-eyes QA pass, 2026-10-24)

Scope: mock mode (`npm run dev`, passcode `tearose`), Chrome via Playwright, 1440×900 and 390×844, light and
dark, print media. Pages: `/`, `/analyze` (gate, intake, simulated run, follow-up), `/run/:id` while streaming and
finished, `/case/jack-daniels-v-vip-products` (the only showcase slug with full mock data), `/method`, a 404.
Console stayed clean (no errors or warnings) on every page in mock mode, before and after the fixes.
`npm run build` passes with no TypeScript errors.

Verdict in one line: the product is coherent and well crafted. The weak spots were legibility of the numbers
(what a "percentile" means), the verdict sitting at the very bottom of the run page, and a few rough edges a jury
would read as unfinished.

## Fixed

1. **Run page, all viewports: the gauge and the memo disagreed on a number.** The junior→senior gauge showed
   `0.47` while the trace and the memo said `0.48` (value 0.475; `toFixed` rounds the binary value down). A jury
   checking "every number traces to a query" would catch this. `format.ts` now has `fixed()` (round half away from
   zero) and `num`, `pct`, `signed`, the gauges and the overlap headline all use it.
2. **Run page, all viewports: the overlap headline label was misleading.** "Symmetric overlap percentile
   (0 = no overlap, 1 = strongest)" invites reading 0.52 as "52% overlap". It now reads "Shared-purchaser
   percentile, both directions averaged", followed by a plain-words reading ("Near the middle of the peer set: no
   signal either way"). The explainer next to it says how the number is made and what 1.00, 0.50 and near 0 mean.
3. **Run page, all viewports: the gauges had no plain-language reading.** Each rank gauge now ends with
   "169 of the 300 pet-supply brands rank lower: near the middle of the peer set: no signal either way." The same
   applies to bridging. The bands come from `readPercentile()` in `format.ts` and are descriptive, never a legal
   conclusion.
4. **Run page, all viewports: the verdict was only at the bottom.** A new **Bottom line** card under the case
   header shows the memo headline, each factor's lean chip, a "Read the memo" link and "Every number below traces
   to one of 14 logged Qloo queries." It is hidden in print because the memo repeats it.
5. **Run page, fame and zone: unlabeled scales.** "Breadth score (0–1)" now has a hint ("1.00 = liked by every
   group; low = a niche audience"). Popularity, heatmap coverage and geographic overlap have one-line hints too.
   The three fame meters are aligned on one baseline.
6. **Run page, 390 px: the gauge scale's "median" label was not under the 50 % tick** because the grid columns were
   `1fr auto 1fr` with unequal content. Now `minmax(0, 1fr)`.
7. **Run page, 1440: the "Who was measured" senior column stretched** to the height of the proxy menu, leaving a
   large empty panel. It is now top-aligned.
8. **Run page, follow-up: there was no completion feedback.** After the answer lands, the box says what was
   answered, that the memo has the new section, and links to it (DESIGN_NOTES rule 9, completion feedback).
9. **Run page, audience comparison: the "distinct" lists were unsorted** (Δ +0.82, +0.73, +0.69, +0.73). They are
   now sorted by |Δ|.
10. **Memo, findings table: a stray short rule under the last row header** (`th` kept its border). Fixed in
    `.table`.
11. **All pages, light mode: a grey smudge in the top-left corner.** It was the off-screen skip link's shadow. The
    skip link now hides with `transform` (no shadow until focused), which also follows the "animate only
    transform/opacity" rule.
12. **Showcase, 1440: four cases sat in a 3 + 1 grid,** and the orphan card looked unfinished. Now 2 × 2 from 720 px.
13. **Showcase, dark: the "Agent judgment" legend swatch was invisible,** and the Memo step's "both" style had no
    legend entry. The swatch has a visible border now, and a third entry was added: "Agent writes, code builds
    the appendix".
14. **Showcase hero copy.** The placeholder "six-figure survey" claim was replaced with the sourced range (see
    `docs/survey-cost-sources.md`), framed as triage before you commission a survey. The three hero facts are
    now the plain questions ("Same customers?", "Famous with everyone?", "Known where?"), each followed by the
    doctrine behind it.
15. **Method, all viewports: the back-test table was a wall of "pending" pills,** which read as broken. Before the
    back-test runs, it now renders as a pre-registered plan with a single status. The table returns automatically
    once `backtest.json` has values.
16. **Method: no plain explanation of a percentile.** A "Reading a percentile" entry now opens "How scores are
    computed". It explains 0.90, 0.50 and near 0, and says explicitly that 0.52 is not "52% of buyers".
17. **Method lead copy:** it now uses the sourced survey cost and time range and the "triage before you commission
    a survey" framing.
18. **All pages: every tab had the same title.** Titles are now per page ("Method · Tea Rose", "Analyze a dispute
    · Tea Rose", "Jack Daniel's v. Bad Spaniels · Tea Rose", "Page not found · Tea Rose").
19. **Analyze, intake: a stale error and an early submit.** Clicking Analyze while a sample was still loading left
    "Paste at least 40 characters" on screen after the text arrived. A successful sample load now clears the
    error, and Analyze is disabled while the sample loads.
20. **Touch targets at 390 px:** disclosure rows ("Passages that drove the extraction", "Candidates considered",
    "Show values as a table") were 18–20 px tall, and the section index links were 29 px. On coarse pointers they
    are now at least 44 px.

## Left for a later pass (with reason)

1. **Showcase → only Bad Spaniels opens in mock mode** (the other three cases say "not in the mock dataset").
   This is correct for mock mode, and the live backend serves all four. Make sure the deployed demo has all four
   cases pre-computed: a jury that clicks "Triple Double" and gets an empty state would lose more than any visual
   polish wins.
2. **Showcase hero, 1440: the right half of the first screen is empty.** A small live "evidence preview" (the
   Bad Spaniels bottom line plus one gauge, linked to the case) would show the product in the first 10 seconds.
   Left out because it needs a design decision and an extra fetch on the landing page.
3. **Run page, trace progress labels at 1440 with a follow-up:** with eight steps the labels truncate
   ("Interp…", "Follo…"). Cosmetic. Use shorter labels or hide them below the bar.
4. **Run page: the Bottom line card appears when the memo finishes,** so content above the reader shifts.
   Chrome's scroll anchoring absorbs it, but Safari does not anchor. A reserved skeleton during the run would fix
   this.
5. **Run page: the sticky section index pill overlaps content under the translucent top bar** (two materials
   stacked, against DESIGN_NOTES rule 5). Merging the index into the top bar on run pages is a layout change, so it
   is out of scope here.
6. **Memo, field references** (`bridging.percentile`, `overlap.symmetric_percentile`) are code chips that do
   nothing when clicked. They could scroll to the matching evidence panel, which would make "every number traces"
   tangible for code-derived numbers too.
7. **Print:** checked with print media at Letter width (the memo, limitations and appendix render; chrome and the
   trace are hidden). The PDF was not paginated visually because no PDF rasterizer is available on this machine.
   Check page breaks inside the findings table and the appendix with a real Print → Save as PDF.
8. **Footer width** is the narrow container on run pages while the run grid is wide. Minor.
9. **oxlint warnings** (set-state-in-effect in `useLiveRun.ts`, fast-refresh exports in `ui.tsx` and
   `TracePanel.tsx`) existed before this pass and do not affect behavior.

## Copy suggestions (hero and method) for a non-lawyer

These suggestions make the value proposition land: a consumer survey is how lawyers usually answer the
relatedness, fame and zone questions, and Tea Rose answers the same questions first, as triage before a survey.

1. **Hero eyebrow:** "The consumer-survey questions, answered from the taste graph first." It names the job before
   the headline does.
2. **Hero, under the headline (shipped in a shorter form):** "Before you commission a consumer survey, see what
   Qloo's taste graph already says: do the same people buy both, is the mark liked by everyone, and where is it
   known. Two minutes, and every number cites the Qloo query behind it."
3. **Hero facts as survey questions (shipped):** "Same customers?", "Famous with everyone?", "Known where?" Each
   is followed by the doctrine in small type, so a non-lawyer reads the question first and a lawyer still sees the
   factor.
4. **Method, opening line:** "A trademark survey asks people questions. Tea Rose asks Qloo's taste graph the same
   three questions and shows the ranks it got back. It is not a survey and does not replace one; it tells you
   whether commissioning one is worth it and what to ask."
5. **Method, the Bad Spaniels lesson:** "Overlap evidence informs two factors; it does not decide a case. In Bad
   Spaniels the relatedness and channel factors favored Jack Daniel's, and VIP still won on remand (2025,
   affirmed 2026). Tea Rose shows the factors; the court weighs them."
