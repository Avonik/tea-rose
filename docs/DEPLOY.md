# Deploying Tea Rose

One container: the FastAPI backend serves the built React frontend. State (Qloo response cache,
live run results, recorded raw responses) lives in Docker volumes. Single worker by design.

## Raspberry Pi 5 (primary)

Prerequisites on the Pi: Docker with the compose plugin; an existing reverse proxy that
terminates HTTPS for the other sites (Caddy, nginx or a Cloudflare Tunnel). The session cookie
is `Secure`, so the public URL must be HTTPS.

```bash
git clone https://github.com/Avonik/tea-rose.git && cd tea-rose
cp backend/.env.example .env     # then edit: QLOO_MODE=live, QLOO_API_KEY, OPENAI_API_KEY, PASSCODE, SESSION_SECRET
docker compose up -d --build     # first build on the Pi takes several minutes (frontend + Python wheels)
curl -s http://127.0.0.1:8000/api/health
```

Reverse proxy: forward the chosen hostname to `127.0.0.1:8000`. The app reads the right-most
`X-Forwarded-For` entry for rate limiting and lockouts, so the proxy must append the client IP
(Caddy and nginx do by default). Caddy example:

```
tearose.example.org {
    reverse_proxy 127.0.0.1:8000
}
```

SSE needs no special proxy configuration in Caddy; for nginx set `proxy_buffering off;` and
`proxy_read_timeout 1h;` on the location.

Update: `git pull && docker compose up -d --build`. Logs: `docker compose logs -f tearose`.

Secrets and caches never enter the image: `.env` is read at runtime via `env_file`, and the cache
directories are volumes. Do not copy `backend/data/cache` or `backend/data/live` into the repo.

## Render (cold mirror)

Web Service from the GitHub repo, environment "Docker", plan Starter (free tier sleeps and would
greet a judge with a 30-60 s spinner). Set the same environment variables in the Render dashboard.
Health check path `/api/health`. Persistent disk mounted at `/app/backend/data/cache` (1 GB) keeps
the Qloo cache across deploys. Render runs amd64; the Dockerfile has no arch-specific steps.

## Pre-submission checklist

- [ ] `QLOO_MODE=live`, hackathon base URL, key valid; `curl /api/health` shows `"mode":"live"`
- [ ] `PASSCODE` set and tested; the passcode goes into the Devpost submission text
- [ ] `SESSION_SECRET` is long and random
- [ ] Caps generous enough for judges (`CAP_LIVE_RUNS_PER_DAY`, `CAP_LIVE_RUNS_PER_SESSION`)
- [ ] Showcase cases pre-computed and committed under `backend/data/showcase/`
- [ ] Mirror deployed and reachable; URL noted privately
- [ ] Cache volume warm: open every showcase case once after deploy
