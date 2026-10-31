# DevOps IaC Spec — itos

- Status: APPROVED FOR BUILD
- Date: 2026-10-25

## 1. Environments

- `dev`: WSL Ubuntu, `uv run uvicorn` (port 8000) + `npm run dev` (port 5173).
- `prod` (v0.2): single host — backend container + static frontend served by nginx. No IaC tool in MVP.

## 2. Docker Compose implementation

```text
compose.yaml               # itos API + web services and optional test profile
compose.aws.yaml           # optional read-only local AWS profile mount
backend/Dockerfile         # python:3.12-slim + locked uv sync; runtime/test targets
frontend/Dockerfile        # node:22-alpine build → nginx:stable-alpine
frontend/nginx.conf        # static SPA + unbuffered /api reverse proxy
```

Start the stack:

```sh
docker compose -f compose.yaml -f compose.aws.yaml up --build -d --wait
```

- Project name and images use `itos`; the assistant is named `wizi`.
- Only web is published, on localhost:8080 by default (`APP_PORT` overrides it).
- Nginx serves the frontend and proxies `/api` to `api:8000`, with SSE buffering disabled.
- Both services run as non-root users and have health checks; web waits for healthy API.
- Named volumes persist API databases and project files across container recreation.
- Secrets are fetched at runtime through the supplied AWS module. Local profiles
  are mounted read-only by the optional AWS override, never copied into images.
- API uses one worker so its per-project cancellation and deletion state is consistent.
- `docker compose --profile test run --rm --build api-tests` runs backend tests in the image.

## 3. CI (v0.2 target, GitHub Actions)

- `backend`: `uv sync && uv run pytest && uv run ruff check`.
- `frontend`: `npm ci && npm run build && npm run lint`.
- Block merge on failure.

## 4. Rules

- Images MUST pin base tags (`python:3.12-slim`, `node:22-alpine`, `nginx:stable-alpine`).
- No secrets baked into images.
