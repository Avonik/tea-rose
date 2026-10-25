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
                              fixtures.py (FixtureClient), cache.py (sqlite)
    scoring/                  score.py (pure functions, NO model calls), universe.py
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
3. **Proxy path is mechanical.** When a brand is not in Qloo, the goods phrase from the document
   goes verbatim to `/v2/tags`; the agent picks only among returned tags; options and choice are
   recorded in `ProxyResolution`.
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
| `resolve` | tool-calling loop (search, tags_search, insights_entities for comparators) | parties → `Resolution` incl. proxies and universes |
| `fetch` | tool-calling loop; the agentic core; retries wider queries on empty results; records give-ups | resolution + routing → `raw` data |
| `score` | pure Python, no LLM | raw → `Evidence` |
| `interpret` | 1 LLM call (optionally stronger model), structured output `list[FactorFinding]` + limitations | evidence → factor findings; blinded names in eval mode |
| `memo` | 1 LLM call → headline + sections; `bottom_line`, appendix and limitations built in code | findings + evidence → `Memo` |
| `followup` | re-enters at `resolve` with an instruction; reruns affected downstream nodes | question → updated result |

`Memo.bottom_line` is one sentence computed by `scoring/bottom_line.py` (`synthesize_bottom_line`) from
the factor leans alone: how many confusion factors support or cut against the senior mark, then fame
and zone, always ending "It is silent on mark similarity, intent and actual confusion." No model
writes it; it never names an outcome. Runs stored before the field existed load with `""`.

Each node emits `TraceEvent`s (`node_started`, `tool_call`, `tool_result`, `decision`, `warning`,
`node_finished`). The API streams them over SSE as they are appended.

Tools exposed to the loops (thin wrappers over `QlooClient`; each appends its `QlooQuery` to
state): `qloo_search`, `qloo_tags_search`, `qloo_insights_entities`, `qloo_insights_tags`,
`qloo_demographics`, `qloo_heatmap`, `qloo_compare`.

## Scoring definitions (v1; tune after the live test)

- **Overlap, one direction:** seed = senior entity id; results = brands filtered to the junior's
  category tags (its universe), `take=50`, pages until the junior appears or 3 pages (150) are
  exhausted. `rank` = 1-based position of the junior entity (or, on the proxy path, the mean rank
  of the comparator brands). `percentile = 1 - (rank - 1) / universe_size`. Not found in 150 ⇒
  percentile 0 and a note.
- **Symmetric overlap** = mean of both directions' percentiles; if only one is computable, use it
  and note it.
- **Bridging:** seed = senior; `insights_tags` → position of the junior's category tag(s) among
  the senior's taste tags; percentile as above.
- **Fame breadth:** from `demographics`, over the 8 buckets (6 age + 2 gender), each value
  clipped to [-1, 1]: `share_pos = #(v > 0) / 8`, `mass_pos = Σ max(v, 0) / max(Σ |v|, eps)`,
  `breadth = clip(share_pos × mass_pos, 0, 1)`. A brand must be positive in many buckets AND
  positive overall to score high (a single positive spike scores low). Plus `popularity`
  percentile and heatmap coverage (share of returned cells with affinity above the median of
  the response; None below 5 cells).
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
