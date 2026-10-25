# Tea Rose architecture

The contract every module and the frontend build against. Change this file first, code second.

## Repo layout

```
backend/
  pyproject.toml              uv project; `uv sync --extra dev`
  src/tearose/
    config.py                 Settings (env / .env), paths
    schemas.py                AnalysisResult, Extraction, Evidence, Memo, TraceEvent  ← THE contract
    qloo/                     models.py (normalized types), parse.py (tolerant parsers),
                              client.py (QlooClient protocol + factory), params.py (exact query
                              params), live.py (HTTP + cache + retries + raw recording),
                              fixtures.py (FixtureClient), cache.py (sqlite), names.py (brand
                              name matching), taxonomy.py (brand-genre tree + goods mapper)
    scoring/                  score.py (pure functions, NO model calls), universe.py,
                              bottom_line.py, describe.py (fact sentences for the prompts)
    agent/                    LangGraph graph: state.py, graph.py, nodes/*.py, tools.py, prompts/*.md,
                              llm.py (OpenAI-compatible chat model factory + fake model for tests)
    api/                      FastAPI: app.py, auth.py, limits.py, routes_*.py, sse.py, showcase.py
    eval/                     back-test harness: run_backtest.py, baselines.py, labels loader
  fixtures/qloo/*.json        synthetic, doc-shaped responses (today); never live data
  data/samples/*.txt          public court documents for extraction tests
  data/showcase/*.json        pre-computed AnalysisResult per showcase case (committed)
  data/cache/, data/live/, data/runs/   gitignored
  eval/cases_candidates.csv   pre-registered labels (committed BEFORE any score is computed)
  tests/
frontend/                     Vite + React + TypeScript; `npm run build` → frontend/dist (served by FastAPI)
docs/                         this file, qloo-api-notes.md, survey-cost-sources.md
```

## Principles

1. **Agent decides what to measure; code decides the number.** `scoring/score.py` is pure
   Python with unit tests and no model call. The LLM chooses entity IDs, tag IDs, universes and
   words; it never produces or adjusts a score.
2. **Every number cites a query.** Each Qloo call returns `(data, QlooQuery)`. Queries accumulate
   in the run state and appear in the memo appendix and in the trace.
3. **Proxy path is mechanical.** When a brand is not in Qloo, the goods phrase is mapped onto
   Qloo's brand taxonomy (`urn:tag:genre:brand`); the agent picks only taxonomy nodes, each with
   a fit label (exact | partial | nearest); options, choice and fit are recorded in
   `ProxyResolution`. Free-text `/v2/tags` on the verbatim phrase is only the last resort.
4. **Ranks, not raw affinities.** Qloo normalizes affinity per query. Overlap is expressed as the
   junior's rank among its category peers when seeded by the senior (and vice versa).
5. **Fixtures today, live Monday.** Nothing above `qloo/` knows which client it is talking to.
6. **Neutral memo.** Same output for both sides; the fixed "what this cannot tell you" list is
   always present.
7. **No LLM in tests by default.** Tests use a scripted fake chat model; `@pytest.mark.llm`
   tests run only with `--run-llm`.

## Agent graph (LangGraph)

State: `AgentState` (TypedDict) holding `input_text`, `extraction`, `routing`, `resolution`,
`raw` (RawData), `evidence`, `memo`, `queries: list[QlooQuery]` (accumulating reducer),
`followup_question`, `blind`, `errors`, `mode`, `run_id`. Trace events are NOT in the state:
nodes and tools emit them straight to the `RunHandle`, so they reach the SSE stream live.
Every `QlooQuery` gets a stable `id` ("q7") when recorded; evidence refs and `tool_result`
events carry that id, and the memo appendix lists queries by it.

Entry: a conditional edge sends a run with `followup_question` set to the `followup` node,
which re-enters at `resolve` (re-resolve goods / add comparator / change universe) or at
`score` (recompute only).

Nodes, in order:

| Node | Type | Input → output |
| --- | --- | --- |
| `extract` | 1 LLM call, structured output `Extraction` | document text → parties, marks, goods (verbatim), channels, claims |
| `route` | 1 LLM call, structured output `RoutingDecision` (with deterministic guardrails: dilution pleaded ⇒ fame; priority ⇒ zone; confusion ⇒ overlap + bridging) | extraction → analyses to run |
| `resolve` | tool-calling loop (search, tags_search, insights_entities for comparators) + brand taxonomy in the prompt | parties → `Resolution` incl. proxies and universes |
| `fetch` | tool-calling loop; the agentic core; retries wider queries on empty results; records give-ups | resolution + routing → `raw` data |
| `score` | pure Python, no LLM | raw → `Evidence` |
| `interpret` | 1 LLM call (optionally stronger model), structured output `list[FactorFinding]` + limitations | evidence → factor findings; blinded names in eval mode |
| `memo` | 1 LLM call → headline + sections; `bottom_line`, appendix and limitations built in code | findings + evidence → `Memo` |
| `followup` | re-enters at `resolve` with an instruction; reruns affected downstream nodes | question → updated result |

`Memo.bottom_line` is one sentence computed by `scoring/bottom_line.py` (`synthesize_bottom_line`) from
the factor leans alone: how many confusion factors support or cut against the senior mark, then fame
and zone, always ending "It is silent on mark similarity, intent and actual confusion." A clause
whose counted findings all have `low` confidence carries " (low confidence)". No model
writes it; it never names an outcome. Runs stored before the field existed load with `""`.

### Resolve, proxy and universe (after the live spike)

- **Hit or miss.** `/search` returns unrelated top hits for small brands, so nobody takes "the
  first result". Agent: the model judges hit vs miss from name, disambiguation, popularity and
  categories; no entity id ⇒ proxy path. `qloo/names.py` is only a guardrail there: a pick whose
  normalised name is not similar to the party's marks/name is kept but flagged ("Name check" in
  `disambiguation_note` and a trace warning). Back-test (harness v3): the same resolve node by
  default (`--resolver agent`); `--resolver rule` = strict code rule `pick_by_name`
  (normalised exact, else fuzzy: all query tokens + at most one extra token or difflib ≥ 0.9,
  else miss; recorded as `exact` / `fuzzy:<ratio>` / `miss`), which the agent resolver also
  records next to its pick for comparison. Both: same entity on both sides ⇒ junior miss.
- **Brand taxonomy.** `qloo/taxonomy.py` harvests the ~177-node `urn:tag:genre:brand` tree with
  26 letter queries to `/v2/tags` (cached, memoised per client). `map_goods_phrase` scores nodes
  by token overlap with name and path plus a small synonym table and labels the fit: `exact`
  (head noun names the node), `partial`, `nearest` (no node fits, e.g. dog toys → Pet Food: the
  memo limitations then say "nearest category, no exact match in Qloo's brand taxonomy"). The
  agent sees the whole tree plus code suggestions and returns `proxy_taxonomy_choices`; code
  validates ids and falls back to the mapper, then to free-text `/v2/tags`.
- **Comparators.** The model's searched brands count if they carry a chosen tag or a descendant
  of it. With fewer than 2 kept, code fills up to 3 by the back-test's rule
  (`scoring/comparators.py`: brands seeded by the other side, filtered to the proxy tags, top 3
  by popularity); `ProxyResolution.comparator_source` records `agent` / `rule` / `mixed`.
- **Universe of a resolved brand** (`scoring/universe.py`, shared by the agent's `resolve` node
  and the back-test). The brand's OWN `urn:tag:genre:brand` tags from its `/search` result (what
  the brand IS: a sneaker brand carries fashion, fashion:footwear, fashion:footwear:sneakers),
  most specific nodes only: any node that is an ancestor of another is dropped, depth >= 2 is
  preferred (a lone top family such as "fashion" only when nothing deeper exists), up to 3.
  Source recorded as "entity own tags"; the model's own universe proposal is not used then.
  Fallback only for a brand without own brand-genre tags: its top 5 insights tags with
  `filter.tag.types=urn:tag:genre:brand` (source "insights tags (fallback)"). Those describe what
  the brand's AUDIENCE likes, which is why they stopped being the primary rule after back-test
  run 1 (a sneaker brand came out as "Food & Beverage"). Then the model's choice, then the goods
  phrase. `pick_category_tags` prefers genre:brand tags on the free-text path.
- **Compare.** `/v2/analysis/compare` returns shared `tags` (query.score), each side's own `a` /
  `b` tags and `matchEntities`. Empty shared tags (a thin brand) is "insufficient data", never
  "no overlap".

Each node emits `TraceEvent`s (`node_started`, `tool_call`, `tool_result`, `decision`, `warning`,
`node_finished`). The API streams them over SSE as they are appended.

Tools exposed to the loops (thin wrappers over `QlooClient`; each appends its `QlooQuery` to
state): `qloo_search`, `qloo_tags_search`, `qloo_insights_entities`, `qloo_insights_tags`,
`qloo_demographics`, `qloo_heatmap`, `qloo_compare`. The direct target-affinity lookup
(`qloo_target_affinity` in the trace) is code-only: the fetch node's data plan holds one per
overlap direction and target, run after the paging.

## Scoring definitions (v1; tune after the live test)

- **Overlap, one direction:** seed = senior entity id; results = brands filtered to the junior's
  category tags (its universe), `take=50`, pages until the junior appears or 3 pages (150) are
  exhausted. `rank` = 1-based position of the junior entity (or, on the proxy path, the mean rank
  of the comparator brands). `percentile = 1 - (rank - 1) / universe_size`.
- **Censoring (harness v2).** A target not in the scanned list (not within 150, or not in an
  exhausted list) has an unknown rank beyond the depth: `rank` and `percentile` are None and
  `*_censored = true` (v1 counted it as rank 151, percentile 0). On the proxy path one missing
  comparator censors the direction.
- **Direct target affinity and affinity ratio (harness v2).** Per direction and target one extra
  call: `/v2/insights` with the same `filter.type`, `signal.interests.entities` and `filter.tags`
  plus `filter.results.entities=<target>` returns that one entity with its `query.affinity`,
  whatever its rank (live check: rank 399). Stored per direction: `target_affinity` (mean over
  comparators on the proxy path), `top1_affinity` and `last_scanned_affinity` of the paged list,
  `depth_scanned`. `affinity_ratio = target_affinity / top1_affinity`, clipped to 0..1, is
  available whenever the lookup succeeds, censored or not ("affinity 0.66 to X's audience, 0.61
  of the strongest brand in the category, beyond the 150 strongest").
- **Symmetric overlap** = mean of both directions' (uncensored) rank percentiles; if only one is
  available, use it and note it; None if neither. `symmetric_affinity_ratio` = mean of the
  available direction ratios.
- **Bridging:** seed = senior; `insights_tags` → position of the junior's category tag(s) among
  the senior's taste tags (top 50 brand-genre tags); percentile as above. With a ~177-node
  taxonomy, absence of the leaf is weak evidence, so when no leaf is present the code climbs the
  taxonomy (strip the last `:` segment, repeatedly, never to the bare `urn:tag:genre:brand`
  root) and takes the nearest ancestor present: `category_rank_among_senior_tags` = the
  ancestor's rank k, `percentile = (1 - (k - 1) / N) × 0.5^levels`, `matched_tag_*` and
  `ancestor_levels` record it, note "leaf absent; parent <name> at rank k". Only when no
  ancestor appears either is the percentile 0 (with a note).
- **Fame breadth:** Qloo demographics are relative indices (over/under-indexing against a
  baseline, about -1..1), not shares, so breadth is an evenness measure over the 8 values
  (6 age buckets + 2 genders), each clipped to [-1, 1], missing = 0:
  `breadth = clip(1 - mean(|v|), 0, 1)`. Flat zeros ⇒ 1.0, mild deviations score high, a strong
  skew in any bucket (+0.9 in one, -0.9 elsewhere) scores low. `breadth_age` / `breadth_gender`
  are the same formula over the age or gender values alone. Plus `popularity` percentile and
  heatmap coverage (share of returned cells with affinity above the median of the response;
  None below 5 cells). `fame_score` = mean(breadth, popularity, coverage), None unless all
  three are present. `skew_description` names the strongest age buckets / gender.
- **Fact sentences:** `scoring/describe.py` (`describe_evidence(evidence, resolution)`) turns
  every number into plain-English sentences per analysis (who is ranked among whom, comparators
  "standing in for" a proxied party, universe sizes, ordinal percentiles, 2-decimal scores,
  "no data", and "small category, rank is coarse" below 20 brands). The interpret and memo
  prompts get these as their FACTS block and may take numbers only from them.
- **Zone concentration:** Gini coefficient of heatmap affinities across cells (0 = uniform,
  1 = concentrated); `top_regions` = cells aggregated by `label` or by 1-decimal lat/lon bins.
  `geographic_overlap` = cosine similarity of the two sides' binned affinity vectors.

All functions take normalized models (`Entity`, `Tag`, `Demographics`, `HeatmapPoint`) and return
the `*Evidence` schemas. They must be total: missing data ⇒ `None` fields + a note, never an
exception.

## HTTP API (FastAPI, prefix `/api`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/health` | – | `{status, mode, version}` |
| GET | `/api/showcase` | – | `list[ShowcaseSummary]` |
| GET | `/api/showcase/{slug}` | – | `AnalysisResult` (pre-computed, cached) |
| GET | `/api/samples` | – | names of sample documents for the intake dropdown |
| GET | `/api/samples/{name}` | – | the sample text |
| POST | `/api/auth/login` | – | body `{passcode}` → sets signed HttpOnly cookie; 5 failures/IP ⇒ 15-min lockout |
| POST | `/api/auth/logout` | cookie | clears cookie |
| GET | `/api/auth/me` | – | `{authenticated, runs_left_today, runs_left_session}` |
| POST | `/api/analyze` | cookie | body `{text}` or multipart `file` (pdf/txt) → **202** `{run_id}`. Errors: 400 empty/unreadable, 413 > 2 MB, 415 wrong type, 422 bad JSON, 429 `{detail, kind:"cap"}` with Retry-After (UTC midnight), 503 engine unavailable. Input is validated before a cap is consumed |
| GET | `/api/analyze/{run_id}/events?after=N` | cookie | SSE: `event: trace` / `id: <seq>` / `data: <TraceEvent JSON>` for each event (replays those after `N` or `Last-Event-ID`, then live), then one `event: done` with `{status, error}`. Ping every 15 s |
| GET | `/api/analyze/{run_id}` | cookie | `AnalysisResult` (current state, partial while running); 403 for another session's run |
| POST | `/api/analyze/{run_id}/followup` | cookie | body `{question}` (1..2000 chars) → **202** `{run_id}`; 409 while the run is still running |
| GET | `/api/limits` | – | `{daily_cap, daily_used, session_cap, live_mode_enabled}` for the UI banner |

Static: everything not under `/api` serves `frontend/dist` (SPA fallback to `index.html`).

Cookies: `tearose_session`, signed with `itsdangerous`, `HttpOnly; Secure; SameSite=Lax`,
TTL 12 h; logout revokes the session id in memory. Login: 503 when no passcode is configured;
401 wrong passcode; after `login_max_failures` failures per IP, 429 `{kind:"lockout"}` for
`login_lockout_minutes`. Rate limit: 60 req/min per IP on `/api/*`, 429 `{kind:"rate_limit"}`
(in-memory token buckets; single process). Client IP = right-most `X-Forwarded-For` entry (the
hop our own reverse proxy appended), else the socket address. All session, cap and ownership
state is in memory on `app.state.ctx`; a restart forgets run ownership (reloaded runs 403).

## Frontend (React + Vite + TS)

Pages:

1. **Showcase** (`/`): the product's front door. Cards for pre-computed cases; one line of
   finding each. "Try your own" → Analyze.
2. **Analyze** (`/analyze`): passcode gate (if not authenticated), then intake: paste text, upload
   PDF, or pick a sample. Submit → navigates to the run page.
3. **Run** (`/run/:id` and `/case/:slug`): left column live trace (streamed), main column the
   evidence board (overlap gauge + peer tables, audience comparison, fame panel with the
   6×2 demographic chart, zone map with MapLibre), then the memo with the limitations box and
   query appendix. Follow-up question box at the end (live runs only). Print stylesheet for PDF.
4. **Method** (`/method`): how it works, what Qloo is, what the scores mean, the back-test table,
   the limitations, the "agent decides what to measure, code decides the number" explanation.

Design: follow the apple-design skill (github.com/emilkowalski/skills/skills/apple-design).
Dev: Vite proxies `/api` to `http://localhost:8000`. Build output is `frontend/dist`.

## Conventions

- Python 3.12, ruff (line length 100), type hints everywhere, `async` for I/O.
- Do not edit `pyproject.toml` dependencies without saying so; one owner for that file.
- Secrets only via env / `.env` (gitignored). `.env.example` documents every variable.
- Commit messages: imperative, one line, no trailers. Commits are made by Julian (or by the
  coordinator on his behalf); subagents do not run git.
