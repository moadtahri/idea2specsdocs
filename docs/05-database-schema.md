# Database Schema — idea2specsdocs

- Status: APPROVED FOR BUILD
- Date: 2026-10-26

## 1. MVP Decision (Binding)

**Local SQLite only — no server DB process.** Two persistence layers:

1. **LangGraph checkpoints** (conversation + agent state, resumable threads):
   `backend/data/<project_id>.db` via `langgraph-checkpoint-sqlite` `SqliteSaver`.
   Managed by the agent runtime — no hand-written schema.
2. **Project registry** (own SQLite file `backend/data/app.db`, hand-managed):

```sql
CREATE TABLE projects (
  id TEXT PRIMARY KEY,            -- uuid
  title TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  created_at TEXT NOT NULL,        -- ISO-8601
  updated_at TEXT NOT NULL
);
```

3. **Handover docs** as plain Markdown files (NOT in SQLite):
   `backend/projects/<project_id>/docs/<slug>.md`, slugs fixed in `04-api-specification.md`.

## 2. Rules

- `backend/data/*.db` MUST be git-ignored; never commit user threads.
- Doc writes go through agent tools + HITL only — no direct route writes its own content.
- Any new table/column MUST update this doc + API spec first.
- Postgres migration is v0.2+ only and requires a new contract version.
