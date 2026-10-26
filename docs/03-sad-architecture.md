# SAD / Architecture — idea2specsdocs

- Status: APPROVED FOR BUILD
- Date: 2026-10-25

## 1. Overview

Monorepo, two runtime processes in dev, one static bundle + one API in prod.
Agent runs server-side inside FastAPI; frontend is a thin streaming chat client.

```text
Browser (React SPA, SSE chat)
   │  POST /api/projects → {project_id, thread_id}
   │  POST /api/chat (SSE: tokens, tool_calls, subagents, interrupts, docs)
   ▼
FastAPI (uvicorn)
   ├── routes: projects CRUD, chat SSE, docs read/download, approvals resume
   └── agent/factory.py → create_deep_agent(...) + 7 subagents + tools
           │  SqliteSaver backend/data/<project_id>.db (checkpoints)
           ▼
projects/<id>/docs/*.md  (9 handover docs, written only after HITL approval)
```

## 2. Components (Contract)

- `frontend/`: Vite React-TS chat SPA. Talks to backend via `src/api.ts` (SSE reader).
  Renders markdown messages, subagent activity, approval cards, doc viewer + download.
  No LLM calls from browser.
- `backend/app/main.py`: routes only — health, projects, chat SSE, docs, approvals.
- `backend/app/agent/factory.py`: builds the deep agent (system prompt, subagents, tools,
  backend, checkpointer, interrupt_on). Only place that imports `deepagents`.
- `backend/app/agent/tools.py`: custom tools (`generate_doc`, `update_doc`, `list_docs`,
  cost estimator). Pure + tested; no FastAPI imports.
- `backend/app/agent/prompts.py`: orchestrator system prompt + 7 subagent prompts.
- `backend/app/schemas.py`: Pydantic v2 chat/doc/project models. Mirrored in frontend types.
- `backend/app/store.py`: SQLite + filesystem project store (threads, checkpoints path, docs I/O).

## 3. Module Layout (Binding)

```text
idea2specsdocs/
├── docs/                  # team contracts (this folder)
├── backend/
│   ├── pyproject.toml
│   ├── data/              # *.db (git-ignored)
│   ├── projects/<id>/docs/*.md
│   └── app/{__init__,main,schemas,store,agent/{__init__,factory,tools,prompts}}.py
├── frontend/
│   ├── package.json, vite.config.ts, index.html
│   └── src/{main.tsx,App.tsx,api.ts,components/{Chat,Approvals,DocViewer}.tsx,styles.css}
└── infra/ (v0.2: docker-compose.yml, Dockerfiles)
```

## 4. Key Design Rules

- Backend validates all input with Pydantic; frontend validates for UX only.
- CORS: allow `http://localhost:5173` in dev only.
- Errors: backend returns `{detail}` with correct status; frontend maps to user message.
- Agent filesystem tools are scoped to `projects/<id>/` (permissions); no repo-wide writes.
- Doc writes flow: agent proposes → `__interrupt__` → user approve/edit/reject → write.
