# Tea Rose: the story the site tells

Status: proposal, 2026-10-25. Design stays frontend-v2 as built; this document decides the
narrative, the order of sections and the copy rules. Terms used here: the **senior brand** is the
older brand that sends the letter; the **junior** is the newcomer it accuses. On the site we avoid
both words where a brand name can stand instead.

## One sentence

Trademark fights turn on who the customers are. Courts pay for surveys to find out. Tea Rose reads
the dispute and answers the customer questions from Qloo's taste graph in about a minute, then says
exactly what it cannot tell you.

## What we claim, and what we never claim

Claim: before anyone spends $15,000 to $100,000 and six to eight weeks on a consumer survey, you can
know in a minute what the audience data says about the two brands: whether their fans overlap, how
widely the older brand is known, and where. Every number traces to a Qloo query. For dilution and
geographic disputes this is direct evidence; for confusion it is the groundwork a survey is later
commissioned to confirm.

Never: "replaces a survey", "predicts the winner", any percentage that sounds like a confusion rate.
A survey shows real people the two products; taste data cannot. Of the eight or so questions a court
weighs, Tea Rose informs three. Bad Spaniels is the proof: the court found whiskey drinkers and
pet-product buyers do overlap, and the dog toy still won on parody. Overlap informs, it does not
decide. That sentence is the spine of the site.

## Home page, in order

### 1. Hero, pinned to scroll (three beats)

The scroll-lock idea stays, but what counts down is time, not money. Counting money down to cents
would say "replaces the survey", which is the one thing we must not say. Counting weeks down to a
minute is true, demonstrated by every showcase run, and still dramatic.

- Beat 1, the stake. Display type: **$15,000 to $100,000.** Under it: "Six to eight weeks. That is
  what a consumer survey costs when two brands fight over who their customers are." Caption with the
  source (docs/survey-cost-sources.md).
- Beat 2, the turn. As the user scrolls, the dollar figure stays, the duration under it morphs from
  **6 to 8 weeks** down to **about one minute**. Copy: "Before you spend it, know what the audience
  data already says."
- Beat 3, the promise. The figure fades, the headline settles: **Trademark evidence from the taste
  graph.** Two pills: "Open a case" and "Analyze a document". The scroll unlocks here.

Motion rules (apple-design skill): one scroll-driven progress value drives all three beats,
interruptible at any point, no autoplay. `prefers-reduced-motion` renders the three beats stacked
with no pinning. Keyboard users get the same content in the same order.

### 2. The three questions a judge asks about customers

Three grouped rows, each with the question in plain words, what we measure, and what a court does
with it:

- **Do the same people buy both?** Where each brand ranks among the other's fans, both directions.
  Feeds "related goods" and "same channels and purchasers", two of the confusion factors.
- **Is the older brand famous with everyone, or only with its own crowd?** How evenly it is liked
  across ages and genders, plus national reach. The threshold question for a dilution claim.
- **Where is it actually known?** The affinity map. The question in geographic disputes over an
  unregistered name.

### 3. Watch it read a real case

The existing device frame with the live Bad Spaniels preview: the bottom line sentence and the three
gauges. Caption: "Read from the complaint, resolved against Qloo, scored in code. 24 queries, 57
seconds."

### 4. Does it hold up?

The back-test told as a paragraph, not a table. "We checked it against 80 decided cases. Where both
brands are in Qloo, the audience signal agrees with the court's finding on related goods and shared
customers in 88% of pairings, against 67% for the obvious rule 'same product category'. Where one
side is a company Qloo does not know, we fall back to its product category and the memo says so;
that fallback is only as good as the category." A link "See the full report, including the two times
we changed our method and why" leads to the Method page. Honesty is the feature here; judges with an
AI reviewer will check.

### 5. Five famous fights

The case list, one line per case: what the court decided, what the taste data shows. Bad Spaniels
leads because of the twist.

- **Jack Daniel's v. Bad Spaniels.** Court: whiskey drinkers and pet buyers overlap, parody wins
  anyway. Data: supports Jack Daniel's on two of three confusion factors and on fame.
- **Starbucks v. Charbucks.** Court: factors favoured Starbucks, dilution still denied. Data: 80th
  percentile overlap, supports Starbucks on both measured factors and on fame.
- **Louis Vuitton v. Chewy Vuiton.** Court: parody wins. Data: overlap present but measured through
  a nearest-category stand-in, so the memo stays neutral and says why.
- **Coach v. Triumph Learning.** Court: handbags and test prep are unrelated. Data: Coach's audience
  does not extend to educational publishing. Agrees.
- **Vans v. MSCHF.** Court: injunction for Vans. Data: 98th percentile overlap. Agrees.

### 6. What it will not tell you

The fixed limitations as a short list: whether the marks look alike, whether the newcomer copied on
purpose, whether anyone has actually been confused, how careful these buyers are. "Not a survey. Not
a verdict. A tool for counsel."

### 7. How it works

The existing seven-step timeline, collapsed to one line per step by default, expandable. Principle
line kept: "The agent decides what to measure. Code decides the number."

### 8. Analyze your own

The passcode entry and the intake. Caps stated plainly.

## Case page, in order

The answer first, then why, then how. Each layer is one scroll deeper and the nav chips follow.

1. **Header.** Case title, year, court. The two brands as chips (dot colours as today). One split
   line: "The court decided: ..." / "The taste data shows: ...". For the showcase cases these two
   sentences are hand-written content (new content file, per slug); for live runs the first half is
   omitted.
2. **Bottom line.** The existing card: headline, the computed bottom-line sentence, the five leans.
3. **The three questions.** One block per question, led by a plain sentence, then its gauge or map
   (existing panels). For a stand-in brand the block starts with "Measured through stand-ins:
   Pedigree, Blue Buffalo" so nobody misses it.
4. **What this means.** The memo's summary and factor-by-factor findings. Lawyer prose, as written.
5. **What it cannot tell you.** The limitations list, including the case-specific ones.
6. **How we got here.** Collapsed: which Qloo entities were chosen and why (resolution card), the
   query appendix, the agent trace in the sheet. Default closed on case pages, open while a live run
   streams.

Everything below item 3 is "more detail if you want it". Nothing technical appears above it.

## Method page

Plain English first: "How to read a memo" (what a lean means, what a percentile means here, why a
small category is coarse), then the glossary, then the back-test story in three short paragraphs (run
1 and what was wrong with it, run 2, run 3 with the product's own resolver), then the formulas behind
"Show the math" expanders. The deviations are presented as what they are: we found two measurement
errors and one design error, dated them, kept every report.

## Copy rules for every page

- Brand names, not roles. "Jack Daniel's" and "the dog toy", not senior and junior, except in the
  glossary and the memo.
- Define a legal term the first time it appears on a page, in the same sentence.
- Numbers as ordinals or whole percentages. Never a raw float.
- Each section answers one question that a reader would actually ask, in its title.
- Say who did what: "the model picked", "code computed", "Qloo returned".
- One honest caveat per result, in the same breath, never a footnote.

## Decisions this document fixes

- frontend-v2 becomes the served frontend (config default, Dockerfile, README).
- The scroll-pinned hero counts time down, not money.
- The back-test appears on the home page as one paragraph with two numbers and a link, nothing more.
- Court outcomes for the five showcase cases are hand-written content, two sentences each.
- Technical detail lives below the fold or behind expanders, on every page.
