# Tea Rose

**Trademark evidence from the taste graph.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Qloo Agentic Hackathon 2026](https://img.shields.io/badge/Qloo-Agentic%20Hackathon%202026-8a2be2.svg)](#acknowledgements)
[![Python 3.12 | React](https://img.shields.io/badge/stack-Python%203.12%20%7C%20React-informational.svg)](#run-it)

## The question

Every trademark fight asks the same question: who are the customers? Today the answer is a consumer
survey that costs $15,000 to $100,000 and takes weeks to two months
([sources](docs/survey-cost-sources.md)). Tea Rose reads the filed pleading (the complaint, plus the
defendant's answer where the docket has one) and answers the customer questions from the taste graph
of Qloo, a company that maps what people like across brands, music, film, food and places, in about
two minutes. Then it gives counsel a preliminary read of the whole case, and says plainly what it
cannot tell you.

## What you get

Each case page, live or pre-computed, has the same layers:

- **The three questions a judge asks about customers**, each answered from Qloo:
  - *Do the same people buy both?* Where each brand ranks among the other's fans, checked in both
    directions. This feeds two factors of *likelihood of confusion* (whether buyers would mistake
    who makes the product): related goods, and the same buyers.
  - *Is it famous with everyone?* How evenly the older brand is liked across ages and genders, and
    how far its reach extends. This is the threshold for *dilution*: only a name the general public
    knows can stop a look-alike, even in an unrelated market.
  - *Where is it actually known?* The affinity map: the regions where the people who like the brand
    live. This settles fights over an unregistered name, which is protected only where the public
    already knows it.
- **The preliminary read.** Which way the case leans (toward the older brand, the newcomer, or too
  close to call), how confident the agent is, what the case turns on, the strongest defence, and
  what could flip it. It is read from the pleadings and covers what data cannot measure: how alike
  the marks are, copying on purpose, confusion the parties allege, how careful buyers are, and
  whether the mark can be protected at all.
- **The memo.** A neutral memo for counsel, the same for both sides, ending with a fixed list of what
  the data cannot tell you.
- **A paper trail.** Every number traces to a logged Qloo query, listed in the memo's appendix and
  in the agent trace.

## How it did on 18 real cases

Each case was read from the filed pleadings with the court's decision withheld; then we compared.

| Case | The court | Tea Rose read | Agreement |
| --- | --- | --- | --- |
| Vans v. MSCHF (Wavy Baby) | Ordered the sneakers off the market, upheld on appeal: a distorted sneaker sold as a sneaker is not a protected parody. | Too close to call, moderate confidence: turns on MSCHF's pleaded free-speech and parody defences and how close Wavy Baby's design is to Vans'. | Too close to call |
| adidas v. Skechers | Upheld the order against Skechers' copy of the Stan Smith, lifted it for a second shoe. | Leans toward adidas, low confidence: turns on how alike the shoes are and whether the Stan Smith's look is protectable. Complaint only. | Split result |
| Hermès v. Rothschild (MetaBirkins) | A jury found the NFTs infringed and diluted the Birkin mark; further sales barred. | Too close to call, moderate confidence: turns on whether free-speech protection covers "MetaBirkins" as the name under which the artworks are sold, and whether that use signals Hermès sponsorship. | Too close to call |
| Vans v. Walmart | Stopped Walmart selling look-alike sneakers while the case went on: shoppers likely to be confused. | Leans toward Vans, low confidence: turns on how alike the shoe designs are and the confusion the complaint alleges. Complaint only. | Same way |
| Nike v. StockX (Vault NFTs) | Nike won on counterfeit shoes before trial; the NFT claims settled. | Too close to call, moderate confidence: turns on StockX's defences that it only named the genuine Nike goods it resold. | Too close to call |
| Bang v. Monster (Reign) | Ruled for Monster after trial: same drink, same buyers, but Bang's can design did not identify Bang to shoppers. | Leans toward Bang, low confidence: turns on how alike the cans and names are and whether the alleged confusion holds up. Complaint only. | Other way |
| Jack Daniel's v. Bad Spaniels | Found that whiskey drinkers and pet-product buyers overlap, and the dog toy still won: a parody, no confusion. | Too close to call, moderate confidence: turns on the parody defence and how alike the marks are. | Too close to call |
| adidas v. Thom Browne | A jury cleared Thom Browne of infringing or diluting the three stripes; upheld on appeal. | Too close to call, low confidence: turns on how alike the specific stripe designs are. | Too close to call |
| Stone Brewing v. MillerCoors | A jury found that MillerCoors' "Stone" branding of Keystone Light infringed and awarded $56 million; upheld on appeal. | Too close to call, moderate confidence: turns on MillerCoors' claim that it used "Stone" first, and how buyers see the word on the full Keystone can. | Too close to call |
| Rolex v. BeckerTime | Rolexes refitted with aftermarket parts infringed; upheld on appeal, though Rolex got no profits because it waited too long to sue. | Leans toward Rolex, low confidence: turns on how alike the marks are and the alleged re-marking of altered watches with Rolex's name. Complaint only. | Same way |
| Kraft v. Cracker Barrel | Barred the restaurant chain from selling Cracker Barrel hams in grocery stores, beside Kraft's Cracker Barrel cheese; upheld on appeal. | Leans toward Kraft, low confidence: turns on how alike the marks are and the shared grocery aisles the complaint describes. Complaint only. | Same way |
| In-N-Out v. Smashburger | No ruling on confusion; the burger chains settled. | Leans toward In-N-Out, low confidence: turns on how alike "Double-Double" and "Triple Double" are, and whether that naming pattern points to In-N-Out. Complaint only. | Split result |
| Louis Vuitton v. My Other Bag | Ruled for My Other Bag: a canvas tote with a cartoon of a Louis Vuitton bag is an obvious joke that does not compete; upheld on appeal. | Too close to call, low confidence: turns on whether the tote reads as a parody rather than a sponsored product. Complaint only. | Too close to call |
| AM General v. Activision | Ruled for Activision before trial: Humvees in Call of Duty are artistic realism, and military vehicles and video games are too far apart to confuse buyers. | Too close to call, low confidence: turns on whether showing the vehicle in a game is protected expression. Complaint only. | Too close to call |
| Buffalo Trace v. 1000 Stories | Ruled for the wine after trial: bourbon and bourbon-barrel wine share some shelves, but the labels looked too different to confuse buyers. | Too close to call, low confidence: turns on whether the shared buffalo imagery makes a similar overall impression and whether the trade dress is protectable at all. Complaint only. | Too close to call |
| T-Mobile v. Aio | Stopped Aio using its plum colour, since both sell to the same budget customers, but held T-Mobile's magenta not famous enough for dilution. | Too close to call, low confidence: turns on whether magenta identifies T-Mobile at all and how closely Aio's colour resembles it. Complaint only. | Too close to call |
| Penn State v. Vintage Brand | A jury found Vintage Brand's retro merchandise infringed the university's marks on purpose and rejected its defences. | Leans toward Penn State, low confidence: turns on how alike the vintage designs are to Penn State's registered marks. Complaint only. | Same way |
| Ohio State v. Redbubble | The trial court cleared Redbubble, the appeals court reversed, and the case settled. | Too close to call, low confidence: turns on whether the designs act as a brand or as decoration, including Redbubble's pleaded free-speech defences. | Too close to call |

Tally: same way 4, split result 2, too close to call 11, other way 1. The read never leaned toward
the newcomer in this set: it committed to a side only when the record held the plaintiff's side
alone, and in five of the six newcomer wins it said too close to call. The one "other way" row,
Bang, was read from the complaint alone, and the read had still named the defence that won, that
the can's features are commonplace rather than a sign of who makes the drink.

The court's decision was withheld from the agent, but the model may still know how famous cases
ended; treat this as a demonstration, not a test. Where a brand is not in Qloo, it is measured
through stand-in brands from its category, and the case page says so above the result. Where only
the complaint was on the record ("Complaint only"), the read hears one side and its confidence is
capped at low.

**The data, checked separately.** We tested the audience measure itself against 80 decided cases,
labelled from the court opinions before any Qloo data was pulled. Where both brands are in Qloo, it
tells the courts' "related goods" findings from the "unrelated" ones well: in 88 of 100 random pairs
of a related and an unrelated case, it ranks the related one higher. That rests on the 14 cases
where both brands are in Qloo and the court decided the point, a small sample; with stand-ins
included it does no better than the plain rule "same product category". Method and full report:
[backend/eval/README.md](backend/eval/README.md) and [backend/eval/results/](backend/eval/results/).

## How it works

**The agent decides what to measure. Code decides the number.**

1. **Extract.** The model reads the pleadings: parties, marks, goods quoted verbatim, claims.
2. **Route.** The model decides which analyses the dispute calls for. Dilution pleaded means fame is
   measured.
3. **Resolve.** The model finds each brand in Qloo. For a company Qloo does not know, it picks three
   stand-in brands from a shortlist code builds, and decides whether that category is close enough
   to measure.
4. **Fetch.** The agent calls Qloo, retries wider when a query comes back empty, and logs every call.
5. **Score.** Code computes ranks and percentiles: tested Python, no model, never a raw affinity score.
6. **Interpret.** The model turns the scores into the factors a court weighs and names what is thin
   or stood in.
7. **Assess.** The model gives the preliminary read. The court's decision is never in its input.
8. **Memo.** The model writes a neutral memo; code writes the bottom line and the query appendix.

What the agent (an OpenAI-compatible model, orchestrated with LangGraph) decides:

- what the dispute is about, and which customer questions it raises;
- which Qloo entity each brand is, or that it is not in Qloo;
- for a missing brand, its category, three stand-ins from the shortlist, and whether the category
  is close enough to compare audiences at all;
- how to recover when a Qloo query comes back empty;
- the factor findings, the preliminary read and the memo prose.

What code decides:

- every number: ranks, percentiles, fame breadth, geographic concentration;
- the stand-in shortlist (up to ten brands from the chosen category, by popularity), and that each
  pick is on it;
- the guardrails: the analyses a pleaded claim requires, low confidence for a letter or a one-sided
  record, no percentages or outcome words in the read;
- the one-sentence bottom line, the read line, and the query appendix.

The opponent is never a stand-in: code removes the other side's brand from the shortlist before the
model sees it. Full contract: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## What it will not tell you

- **Whether the marks look or sound alike, whether the newcomer copied on purpose, whether anyone
  has actually been confused, how careful buyers are.** These are read from what the parties
  allege, never measured.
- **Affinity is not confusion.** Shared fans are evidence that the goods are related and reach the
  same buyers; they are not a confusion rate.
- **No survey percentages.** Qloo scores each answer on its own scale, so a score is a position in a
  list, never a share of consumers.
- **Coverage gaps are stated per brand.** Small brands are often missing from Qloo; where stand-ins
  were measured instead, the finding says so.
- **Today's taste, not the year of the dispute.**
- **Not legal advice.** A tool for counsel.
- **The preliminary read is judgment, not measurement.** It is the agent's reading of the pleadings;
  with only the plaintiff's side in the record its confidence is capped at low.

Not a survey, not a ruling: a tool for counsel.

## Run it

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js with npm.

**Backend** (FastAPI; fixture mode runs without any key):

```
cd backend && uv sync --extra dev && uv run python -m uvicorn tearose.api.app:app --reload
```

`uv run tearose` starts the same app with the host and port from the settings. Health check:
`http://localhost:8000/api/health`.

**Frontend** (React + Vite + TypeScript):

```
cd frontend && npm install && npm run dev   # mock mode, no backend needed: http://localhost:5173
cd frontend && npm run dev:api              # against the backend: Vite proxies /api to port 8000
cd frontend && npm run build                # production build; the backend then serves frontend/dist
```

Mock mode replays a bundled demo run; its simulated passcode is `tearose`.

**Configuration.** Copy `backend/.env.example` to `.env` at the repo root (`backend/.env` also
works). Never commit it.

| Variable | Purpose |
| --- | --- |
| `QLOO_MODE` | `fixture` (default, synthetic responses, no key) or `live` |
| `QLOO_API_KEY`, `QLOO_BASE_URL` | Qloo hackathon key and host (`https://hackathon.api.qloo.com`) |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | Any provider that speaks the OpenAI chat API |
| `LLM_MODEL`, `LLM_MODEL_STRONG` | Model for every step (default `gpt-5-mini`); optional stronger model for interpretation |
| `LLM_REASONING_EFFORT` | `low`, `medium` or `high`; dropped automatically if the provider rejects it |
| `LLM_PRICE_INPUT_PER_M`, `LLM_PRICE_OUTPUT_PER_M`, `LLM_PRICE_CACHED_INPUT_PER_M` | USD per million tokens; when the first two are set, every run records its cost next to its token counts (`llm_usage` in the result, `run_finished` in the trace) |
| `PASSCODE`, `SESSION_SECRET` | Live analysis is off while `PASSCODE` is empty; showcase cases are always public |
| `CAP_LIVE_RUNS_PER_DAY`, `CAP_LIVE_RUNS_PER_SESSION` | Live-run caps (defaults 60 and 15) |
| `HOST`, `PORT`, `SECURE_COOKIES` | Server; set `SECURE_COOKIES=false` to log in over plain http locally |

**Pre-computing the showcase.** The cases listed in `backend/data/showcase/manifest.json` run
through the same graph as a live analysis and are written to `backend/data/showcase/<slug>.json`,
which the API loads at startup. Needs an LLM key; the Qloo mode comes from `.env`. From `backend/`:

```
uv run python -m tearose.eval.precompute_showcase --all-analyses               # every case
uv run python -m tearose.eval.precompute_showcase --all-analyses bad_spaniels  # selected cases
```

`--all-analyses` measures all three questions for every case; those the pleading did not raise are
marked "Measured for context: not pleaded".

**The data back-test.** Four idempotent steps, from `backend/` (options such as `--resolver`,
`--only` and `--out` are in [backend/eval/README.md](backend/eval/README.md)):

```
uv run python -m tearose.eval.backtest prepare   # labelled cases -> mapping.csv (no Qloo calls)
uv run python -m tearose.eval.backtest resolve   # identify each brand in Qloo -> resolved.json
uv run python -m tearose.eval.backtest score     # -> scores.json (code only, no model)
uv run python -m tearose.eval.backtest report    # -> backend/eval/results/
```

Live runs write to `backend/eval/`; fixture runs to `backend/eval/_fixture/`.

**Tests.**

```
cd backend && uv run pytest -q                        # no network, no LLM
cd backend && uv run pytest -q --run-llm --run-live   # opt in: real model and live Qloo
cd frontend && npm run typecheck
```

**Deploy.** One container: the backend serves the built frontend. Run `docker compose up -d --build`
with a `.env` at the repo root; reverse proxy, HTTPS and the Render mirror are in
[docs/DEPLOY.md](docs/DEPLOY.md).

## Repository layout

```
backend/
  src/tearose/   agent/ (LangGraph nodes, prompts), scoring/ (pure Python, no model),
                 qloo/ (client, cache, taxonomy), api/ (FastAPI), eval/ (back-test, showcase)
  data/samples/  public court filings used as inputs
  eval/          labelled cases, pre-registered mapping, back-test reports
  tests/
frontend/        React + Vite + TypeScript; site copy in src/content/
docs/            ARCHITECTURE.md, DEPLOY.md, survey-cost-sources.md, qloo-api-notes.md
archive/         earlier frontends, kept for reference; not built or served
```

## Data and privacy

- Qloo responses are cached locally (`backend/data/cache/`, `backend/data/live/`) and never
  committed; Qloo's terms do not allow publishing response data.
- Showcase results contain Qloo-derived data, so they are generated on the server and not committed;
  only the manifest is. A fresh clone shows an empty showcase until you pre-compute it.
- Back-test intermediates (`resolved.json`, `scores.json`) stay local; only the reports are committed.
- The sample pleadings in `backend/data/samples/` are public court records; each file names its case,
  docket entry and source URL in its first lines.
- A document you submit for live analysis is processed on the server running Tea Rose and sent to
  the configured model provider.

## Acknowledgements

- [Qloo](https://www.qloo.com/), for the taste graph and the Agentic Hackathon 2026.
- [CourtListener and RECAP](https://www.courtlistener.com/) (Free Law Project) and
  [GovInfo](https://www.govinfo.gov/), for the filings and opinions.
- The [Caselaw Access Project](https://case.law/) (Harvard Law School Library), for opinion texts.

## Licence

MIT, see [LICENSE](LICENSE). Copyright (c) 2026 Julian Hermes.
