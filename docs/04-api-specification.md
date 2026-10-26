# API Specification — idea2specsdocs (v2 Contract: chat agent)

- Base URL (dev): `http://localhost:8000`
- Content-Type: `application/json` (chat POST is SSE: `text/event-stream`)
- Status: APPROVED FOR BUILD

## Endpoints

### 1. `GET /api/health` → `200 {status: ok, version}`

### 2. `POST /api/projects` → `201 {project_id, thread_id, title}`

- Body: `{ "title": "1-200 chars" }`. Creates `projects/<id>/`, SQLite DB, thread.

### 3. `GET /api/projects` → `200 [{project_id, title, updated_at}]`

### 4. `GET /api/projects/{id}/docs` → `200 {docs: [{slug, title, updated_at}]}`

- Slugs (fixed, in order): `prd`, `technical-spike`, `sad-architecture`, `api-specification`,
  `database-schema`, `security-blueprint`, `devops-iac-spec`, `qa-test-plan`, `runbook`.

### 5. `GET /api/projects/{id}/docs/{slug}` → `200 {slug, markdown}`

### 5b. `POST /api/projects/{id}/uploads` → `201 {attachment_id, filename, content_type, size, text_preview, created_at}`

- Multipart form with one `file` field. Guardrails: max 10 MB (`413`), allowlist
  `text/*`, `application/json`, `pdf`, `doc(x)`, `audio/*` (`415` otherwise).
- Stored on disk at `projects/<id>/uploads/`, metadata in `app.db:attachments`.
- Text files inlined (up to 6000 chars) as agent context; pdf/docx best-effort extraction.

### 5c. `POST /api/transcribe` → `200 {text}`

- Multipart audio blob. Server Whisper (`OPENAI_API_KEY`) when configured,
  else `501` — UI falls back to on-device Web Speech API dictation.

### 6. `POST /api/chat` (SSE stream)

- Purpose: send a user message, stream agent run. Body:

```json
{ "project_id": "uuid", "message": "string (0-8000)", "resume": null, "attachment_ids": ["uuid"] }
```

- Resume after interrupt: `{ "project_id": "...", "message": "", "resume": { "decisions": [...] } }`
- SSE events (`data: <json>\n\n`):
  - `{ "type": "token", "source": "main|<subagent>", "text": "..." }` — chat reply tokens
  - `{ "type": "thought", "source": "...", "text": "..." }` — reasoning/thinking blocks
  - `{ "type": "step", "source": "...", "node": "model|tools|..." }` — graph node completions
  - `{ "type": "tool_call", "source": "...", "name": "...", "args_preview": "..." }`
  - `{ "type": "subagent", "status": "pending|running|complete", "name": "..." }`
  - `{ "type": "todos", "todos": [{ "content": "...", "status": "pending|in_progress|completed" }] }`
  - `{ "type": "interrupt", "interrupt_id": "...", "action_requests": [...], "review_configs": [...] }`
  - `{ "type": "doc_updated", "slug": "...", "title": "..." }`
  - `{ "type": "done", "thread_id": "..." }` and `{ "type": "error", "detail": "..." }`

### 7. Errors

- `404` unknown project; `422` validation; `409` thread busy (one run per project at a time);
  `500` → `{detail}`. Frontend MUST surface `error` events without crashing chat.

## Contract Rules

- Slug list/order MUST match §4 and the 9 `docs/*.md` contracts.
- SSE event `type` strings MUST NOT be renamed without a version bump.
- Frontend types in `src/api.ts` MUST mirror these models exactly.
