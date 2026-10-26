# PRD — idea2specsdocs (Chat-Agent Handover App)

- Version: 0.2.0 (Contract — supersedes 0.1.0 template-generator plan)
- Status: APPROVED FOR BUILD
- Owner: Product / moadtahri
- Date: 2026-10-26

## 1. Purpose

Chat-first app where a project team brainstorms a software idea with an AI agent
(architecture, business logic, constraints, cost, infra, security, timeline, staffing)
and the agent produces/maintains the **9 handover documents** as the contract between teams:

| Phase | Documents |
|---|---|
| Planning | PRD, Technical Spike, SAD/Architecture |
| Development | API Specification, Database Schema, Security Blueprint |
| Deployment & Live | DevOps IaC Spec, QA Test Plan, Runbook/On-Call Docs |

## 2. Users

- Founder/PM/tech lead brainstorming in chat.
- Dev/SecOps/QA consuming generated documents.

## 3. Scope — MVP (Contract)

IN:
- Chat UI: streaming messages, token + tool-call + subagent progress display.
- One persistent project thread with **SQLite memory** — resume discussion, ask follow-ups,
  request recommendations, update the project; agent recalls prior decisions.
- Agent harness: `langgraph` deep-agent (`create_deep_agent`) with subagents per doc domain
  (planner, architect, api-designer, data-modeler, security, devops, qa).
- 9 docs generated and editable via chat (`write_file`/`edit_file` on project docs dir),
  downloadable as Markdown.
- HITL approval before writing/publishing docs.
- Session/project list + resume.

OUT (deferred):
- Multi-user auth, org workspaces, cost dashboard, PDF export, MCP/A2A integrations
  (design API to allow later, do not build).

## 4. Functional Requirements (Normative)

- FR-1: Chat MUST stream tokens, tool calls, subagent progress (SSE).
- FR-2: Memory MUST persist per project in local SQLite; reload/resume restores full thread + docs.
- FR-3: Agent MUST cover all 9 docs; each doc MUST follow its contract in `docs/0x-*`.
- FR-4: Doc writes REQUIRE human approval (HITL) — approve/edit/reject from UI.
- FR-5: Frontend MUST render empty/loading/streaming/error/approval-pending states.
- FR-6: Model provider MUST be env-config (`MODEL=provider:model`).

## 5. Non-Functional Requirements

- Backend: FastAPI + `uv`, Python 3.12, `deepagents`, `langgraph` + `langgraph-checkpoint-sqlite`.
- Frontend: React + TS + Vite, Node 22.
- Dev: WSL Ubuntu 24.04, zsh. SQLite file `backend/data/app.db` (git-ignored).
- No secrets in repo; `.env` only.

## 6. Acceptance Criteria

- [ ] New project → chat → agent asks clarifying questions → drafts all 9 docs with approvals.
- [ ] Close + reopen → thread + docs restored from SQLite.
- [ ] Follow-up ("change DB to Postgres") → agent updates affected docs after approval.
- [ ] Backend down → chat shows error, no crash. `README.md` run steps work verbatim on fresh WSL clone.

## 7. Open Questions

- Q1: Default model provider for MVP? (default: Ollama local; fallback OpenAI-compatible via env)
- Q2: Doc storage: plain files vs virtual-FS-in-SQLite? (default: plain `projects/<id>/docs/*.md` + SQLite checkpoints/threads)
