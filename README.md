# Tea Rose

Trademark overlap evidence agent, built on Qloo's taste graph for the Qloo Agentic Hackathon 2026.

Courts ask whether Jack Daniel's drinkers and dog-toy buyers are the same people. Today that is a six-figure consumer survey. Tea Rose reads a complaint or a cease-and-desist letter, works out which legal questions the dispute turns on, and answers the three that are really questions about consumer taste from Qloo's taste graph:

| Legal question | Where it matters | Qloo evidence |
| --- | --- | --- |
| Do the two brands share purchasers? Are the goods related in consumers' minds? | Likelihood of confusion: relatedness of goods, channels of trade, bridging the gap | Rank of each brand among the other's category peers when seeded by that brand; audience comparison |
| Is the senior mark famous with the general public? | Dilution | Age and gender breadth, popularity, national heatmap coverage |
| Where is the mark actually known? | Common-law priority, the Tea Rose doctrine | Geographic heatmap, concentration index, overlap of the two maps |

The output is a neutral memo for counsel in which every number traces back to a Qloo query, plus an explicit list of what the data cannot tell you.

**Principle:** the agent decides what to measure; code decides the number. The LLM reads the document, chooses doctrines, resolves brands (falling back to product-category proxies when a party is not in Qloo, and saying so) and writes prose. Scores are computed by `scoring/score.py`, which has no model call in it.

## Repository

```
backend/    FastAPI + LangGraph agent + deterministic scoring (Python 3.12, uv)
frontend/   React + Vite + TypeScript (showcase, analyze, run view, method)
docs/       ARCHITECTURE.md (the contract), qloo-api-notes.md, DEPLOY.md
```

## Run locally

Backend (fixture mode works without any key):

```
cd backend && uv sync --extra dev && uv run python -m uvicorn tearose.api.app:app --reload
```

Frontend in mock mode (no backend needed): `cd frontend && npm install && npm run dev`.
Frontend against the backend: `npm run dev:api` (Vite proxies `/api` to port 8000).
Production build served by the backend: `npm run build`, then start the backend; it serves `frontend/dist`.

Configuration: copy `backend/.env.example` to `.env` at the repo root. Live analysis needs `QLOO_MODE=live`, a hackathon `QLOO_API_KEY`, an OpenAI-compatible `OPENAI_API_KEY` and a `PASSCODE`. Showcase cases are pre-computed (`uv run python -m tearose.eval.precompute_showcase`) and served free of charge; live analysis is behind the passcode with daily and per-session caps.

Tests: `cd backend && uv run pytest -q` (no network, no LLM; `--run-llm` / `--run-live` opt in).

Deployment: see `docs/DEPLOY.md` (Docker, Raspberry Pi, Render mirror).

## Status

Built against documented API shapes with synthetic fixtures; live Qloo integration and the pre-registered back-test follow once the hackathon key is active. See `docs/ARCHITECTURE.md`.

## License

MIT, see [LICENSE](LICENSE).
