# Technical Spike — itos

- Status: APPROVED FOR BUILD
- Date: 2026-10-25

## 1. Goal

De-risk stack choices for WSL + uv + FastAPI + React TS + deep-agent harness + SQLite memory.

## 2. Decisions (Binding)

- D1: Backend managed by `uv` (`pyproject.toml`, `.venv` in `backend/`). No pip/poetry.
- D2: Python 3.12, FastAPI >= 0.115, uvicorn standard.
- D3: Agent harness = `deepagents.create_deep_agent` on `langgraph`. Single orchestrator agent
  with 7 domain subagents: planner, architect, api-designer, data-modeler, security, devops, qa.
  Coordinator keeps context lean; each subagent returns concise structured findings.
- D4: Memory = `langgraph-checkpoint-sqlite` (`SqliteSaver`) per-project DB file
  `backend/data/<project_id>.db` + JSON doc files under `backend/projects/<project_id>/docs/`.
  Resume = same `thread_id`. No Postgres in MVP.
- D5: Model via `init_chat_model(MODEL)` from env (`MODEL` string like `openai:gpt-4o-mini`
  or `ollama:qwen3`). No hardcoded keys.
- D6: HITL via `interrupt_on={"write_file": True, "edit_file": True}`; frontend resolves
  interrupts through `POST /api/chat` resume flow.
- D7: Streaming via SSE: backend `agent.astream(..., stream_mode=["messages","updates","custom"], subgraphs=True)`.
- D8: Frontend Vite proxy `/api -> http://localhost:8000` in dev; production builds use `VITE_API_URL`.
- D5: No DB in MVP. History in `localStorage`. v0.2 target: Postgres + SQLModel if needed.

## 3. Risks

- R1: Node missing in WSL — mitigated via tarball install to `~/.local/node`.
- R2: Port conflicts (8000/5173) — configurable via env.

## 4. Outcome

- Proceed with stack above. No further spike required for MVP.
