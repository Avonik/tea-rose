# Tea Rose — single image: built frontend served by the FastAPI backend.
# Multi-arch friendly (amd64 for the Render mirror, arm64 for the Raspberry Pi 5).

# ---- 1. frontend build -------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. backend ---------------------------------------------------------------------
FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --no-dev --no-install-project --frozen 2>/dev/null || uv sync --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --no-dev
COPY LICENSE /app/LICENSE
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Runtime data (cache, runs) lives in a volume mounted at /app/backend/data
RUN mkdir -p data/cache data/runs data/live && useradd -r -u 10001 tearose && chown -R tearose /app
USER tearose
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"
CMD ["uv", "run", "--no-dev", "uvicorn", "tearose.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
