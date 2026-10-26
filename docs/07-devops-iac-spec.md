# DevOps IaC Spec — idea2specsdocs

- Status: APPROVED FOR BUILD
- Date: 2026-10-25

## 1. Environments

- `dev`: WSL Ubuntu, `uv run uvicorn` (port 8000) + `npm run dev` (port 5173).
- `prod` (v0.2): single host — backend container + static frontend served by nginx. No IaC tool in MVP.

## 2. MVP IaC (Binding when `infra/` is created)

```text
infra/
├── docker-compose.yml      # api + web services
├── backend.Dockerfile      # python:3.12-slim + uv sync
└── frontend.Dockerfile     # node:22 build → nginx serve
```

Compose contract:

```yaml
services:
  api:
    build: { context: ../backend, dockerfile: ../infra/backend.Dockerfile }
    ports: ["8000:8000"]
    environment:
      CORS_ORIGINS: "${CORS_ORIGINS:-http://localhost:5173}"
  web:
    build: { context: ../frontend, dockerfile: ../infra/frontend.Dockerfile }
    ports: ["8080:80"]
    environment:
      VITE_API_URL: "http://localhost:8000"
```

## 3. CI (v0.2 target, GitHub Actions)

- `backend`: `uv sync && uv run pytest && uv run ruff check`.
- `frontend`: `npm ci && npm run build && npm run lint`.
- Block merge on failure.

## 4. Rules

- Images MUST pin base tags (`python:3.12-slim`, `node:22-alpine`, `nginx:stable-alpine`).
- No secrets baked into images.
