# Tea Rose frontend v2

A second, independent frontend for Tea Rose. It talks to the same backend API as `frontend/`
and shares its TypeScript contract and mock data, but every page, component and stylesheet is new.
See `DESIGN.md` for the design rules and what changed.

## Run

```
cd frontend-v2 && npm install
npm run dev        # mock mode on http://localhost:5174 (passcode "tearose"), no backend needed
npm run dev:api    # against the FastAPI backend on :8000 (Vite proxies /api)
npm run build      # typecheck + production build to frontend-v2/dist
```

## Switch the backend to this build

The backend serves whatever `frontend_dist` points at (`backend/src/tearose/config.py`, a
pydantic setting). Nothing in `frontend/` needs to change. Either:

- set `FRONTEND_DIST=/absolute/path/to/frontend-v2/dist` in `.env` (or the environment), or
- change the default in `config.py` from `frontend/dist` to `frontend-v2/dist`, and in the
  `Dockerfile` build stage replace `frontend/` with `frontend-v2/`.

To go back, remove the variable or revert the two lines.
