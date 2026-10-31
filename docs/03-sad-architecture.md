# SAD / Architecture — itos

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
   └── agent/factory.py → create_deep_agent(...) + 7 subagents + repo-reader + tools
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
- `backend/app/agent/harness.py`: LangChain middleware every agent runs with (no `deepagents`
  import). Per-run model and tool call limits, a breaker that turns a raising tool into an error
  result and refuses repeated failures (never `write_file`/`edit_file`, which the user approved),
  model retries for transient errors plus an optional fallback model, and the compaction digest.
  `factory.py` replaces Deep Agents' summarizer with these settings: compact past 80k tokens,
  keep the last 24 messages, offload folded turns to `projects/<id>/conversation_history/`.
  Ported from the Canyas director harness (spec `.ai/specs/01-harness-resilience.md`).
- `backend/app/agent/tools.py`: custom tools (`generate_doc`, `update_doc`, `list_docs`,
  cost estimator). Pure + tested; no FastAPI imports.
- `backend/app/agent/prompts.py`: wizi's system prompt (a one-line identity plus the core skill) + 7 subagent prompts
  + `REPO_READER`: a read-only specialist for uploaded source (`factory.repo_reader()`: no register tools, every
  write denied by permission, its own limits). It reads `uploads/<id>/source/` in its own context and returns a
  short report citing files; the discovery gate lets it through before the brief is approved (spec 04).
- `backend/app/agent/skills/wizi-core/`: `SKILL.md`, the core skill always in wizi's system prompt (under 7,000
  characters, test-enforced); `stages/{discovery,drafting,review}.md`; `modes/{feature,cleanup}.md`.
- `backend/app/agent/stages.py`: the stage from project state (discovery until the brief is approved, drafting
  while a document is missing, then review) and the brief's `intake` mode (`idea`, `feature`, `cleanup`).
  `StageMiddleware` appends the stage file, and the mode file for feature and cleanup, to the system message
  before each model call (spec `.ai/specs/02-core-skill-and-stages.md`).
- Decision register (`quality_store.py`): work items carry `owner_type` and `blocked_by` (blockers must already
  exist, so the graph has no cycles); `frontier()` lists what can be decided now. Wizi settles an item from chat only
  with the user's own words (`settle_decision`). `frontend/src/components/DecisionMap.tsx` draws the register as a
  map in the brief panel: one row below the deepest blocker, the frontier glowing, colour by owner
  (spec `.ai/specs/03-decision-ownership.md`).
- Specs stage and agent package (spec `.ai/specs/05-agent-package.md`): after the nine documents, wizi writes
  `projects/<id>/specs/` (`README.md` the plan, `agents.md` the conventions, `NN-<slug>.md` one per slice), each
  on an approval card; `specs.py` reads the plan and tells the stage what is missing. `package.py` builds the zip
  from fixed templates (`package_templates/`: the skill, its task/check/refine procedures, `check_scope.py`,
  `questions.md`) and the project's specs, documents and decision register. The single-file agent bundle stays.
  `package_checks.py` checks the package's files as zipped (spec 06) and reads a returned `.ai/questions.md` into
  stakeholder decisions. `diagrams.py` adds Mermaid diagrams to the readable bundle from the specs and the register.
- Typed approvals (`typed_approval.py`) and questionnaires (`questionnaire.py`): the app, never wizi, turns a typed
  "approve" into a card's decision, and a stakeholder's written answers into settled decisions (spec 03 T5, T6).
- Behaviour evals (`backend/evals/`, spec 07): `python -m evals.run` drives a running server with the real model
  over several trials per case and reports each check's pass rate; graders are unit-tested.
- `backend/app/schemas.py`: Pydantic v2 chat/doc/project models. Mirrored in frontend types.
- `backend/app/store.py`: SQLite + filesystem project store (threads, checkpoints path, docs I/O).

## 3. Module Layout (Binding)

```text
itos/
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
- A tool failure never ends a turn; it comes back to the agent as an error result. Model errors
  that survive retries end the turn with a user-facing SSE `error`. Messages the harness adds for
  the user (`additional_kwargs.itos_source == "harness"`) stream as chat tokens.
