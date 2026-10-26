# Tea Rose frontend

The Tea Rose web app: React + Vite + TypeScript. It talks to the FastAPI backend under `/api`; the
backend serves the production build from `frontend/dist`. See `DESIGN.md` for the design rules.
Earlier frontends live in `../archive/` for reference only.

## Run

```
cd frontend && npm install
npm run dev        # mock mode on http://localhost:5173 (passcode "tearose"), no backend needed
npm run dev:api    # against the FastAPI backend on :8000 (Vite proxies /api)
npm run typecheck  # tsc only
npm run build      # typecheck + production build to frontend/dist
```

The backend picks the build up via `frontend_dist` in `backend/src/tearose/config.py`
(default `<repo>/frontend/dist`, overridable with `FRONTEND_DIST`); the `Dockerfile` builds this
directory in its first stage.
