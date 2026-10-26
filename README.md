# idea2specsdocs

Chat-first app: brainstorm a software idea with a **deep-agent** team
(planner, architect, API designer, data modeler, security, DevOps, QA) and get the
**9 handover documents** as the contract between teams — remembered per-project in
local **SQLite** so you can resume, update, and ask follow-ups.

| Phase | Documents |
|---|---|
| Planning | PRD, Technical Spike, SAD/Architecture |
| Development | API Specification, Database Schema, Security Blueprint |
| Deployment & Live | DevOps IaC Spec, QA Test Plan, Runbook |

## Stack

- **Backend:** FastAPI + `uv` venv (project-specific `backend/.venv`, Python 3.12),
  `deepagents` + `langgraph` + `langgraph-checkpoint-sqlite`, SSE streaming, HITL approvals.
- **Frontend:** React + TS + Vite (Node 22), streaming chat + approvals + doc viewer.
- **Dev env:** WSL Ubuntu 24.04, zsh.

## Run the backend (WSL zsh)

```zsh
cd backend
cp .env.example .env   # set MODEL, e.g. ollama:qwen3 or openai:gpt-4o-mini
uv run uvicorn app.main:app --reload --port 8000
```

Health: http://localhost:8000/api/health — interactive docs: http://localhost:8000/docs

## Run the frontend (WSL zsh)

```zsh
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 (calls `/api`, proxied to the backend).

## How it works

1. Create a project → backed by `backend/data/<project_id>.db` (checkpoints = memory)
   and `backend/projects/<project_id>/docs/*.md` (the 9 docs).
2. Chat streams tokens, tool calls, and subagent progress (SSE).
3. Doc writes pause for your approval (approve/reject) in the chat UI.
4. Reopen the project later — thread + docs resume from SQLite.

## Contracts

`docs/` holds the 9 binding contracts (01-prd → 09-runbook) plus architecture/API/DB/security specs.
