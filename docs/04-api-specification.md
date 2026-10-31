# API Specification — itos (v2 Contract: wizi)

- Base URL (dev): `http://localhost:8000`
- Content-Type: `application/json` (chat POST is SSE: `text/event-stream`)
- Status: APPROVED FOR BUILD

## Endpoints

### 1. `GET /api/health` → `200 {status: ok, version}`

### 2. `POST /api/projects` → `201 {project_id, thread_id, title}`

- Body: `{ "title": "1-200 chars" }`. Creates `projects/<id>/`, SQLite DB, thread.

### 3. `GET /api/projects` → `200 [{project_id, title, updated_at}]`

### 3a. `PATCH /api/projects/{id}` → `200 {project_id, title, updated_at}`

- Body: `{ "title": "1-200 chars" }`. Trims whitespace and rejects an empty name.
- Preserves the project ID, conversation, uploads and documents. Invalidates the
  readable bundle when its project title changes.

### 3b. `DELETE /api/projects/{id}` → `204`

- Immediately cancels wizi and readable-bundle work for this project, waits for
  checkpoint handles to close, then removes its directory, uploads, documents,
  checkpoint database and sidecars, cached readable bundle, attachment rows and
  project record. The UI calls this directly when Delete is clicked.
- New requests for a project being deleted receive `404`.

### 4. `GET /api/projects/{id}/docs` → `200 {docs: [{slug, title, updated_at}]}`

- Slugs (fixed, in order): `prd`, `technical-spike`, `sad-architecture`, `api-specification`,
  `database-schema`, `security-blueprint`, `devops-iac-spec`, `qa-test-plan`, `runbook`.

### 5. `GET /api/projects/{id}/docs/{slug}` → `200 {slug, markdown}`

### 5b. `POST /api/projects/{id}/uploads` → `201 {attachment_id, filename, content_type, size, text_preview, created_at}`

- Multipart form with one `file` field. Guardrails: max 10 MB (`413`), allowlist
  `text/*`, `application/json`, `pdf`, `doc(x)`, `audio/*` (`415` otherwise).
- Stored on disk at `projects/<id>/uploads/`, metadata in `app.db:attachments`.
- Text files inlined (up to 6000 chars) as agent context; pdf/docx best-effort extraction.
- A source `.zip` (same filters: text source only, no dependencies, no `.env`, no traversal) is also written as a
  read-only tree at `uploads/<attachment_id>/source/` with `source-index.md`, for the `repo-reader` specialist; the
  chat names the tree when the attachment is sent. Nothing uploaded is executed (spec 04).

### 5c. `POST /api/transcribe` → `200 {text}`

- Multipart audio blob. The backend fetches `ASSEMBLYAI_API_KEY` through the supplied
  AWS Secrets Manager module, uploads audio to AssemblyAI and polls for completion.
- Missing key: `503`; provider errors or a two-minute deadline: `502` with readable
  retry guidance. The UI retains the recording for Retry or Discard.

### 5d. `POST /api/transcribe/token` → `200 {token, websocket_url, sample_rate}`

- Creates a temporary AssemblyAI streaming token from the AWS-stored key. No
  permanent API key is sent to the browser. Response uses `Cache-Control: no-store`.
- Token redemption window: 60 seconds. Session cap: 360 seconds. The browser stops
  recording at 300 seconds and sends Terminate when stopped or unmounted.
- The browser streams PCM16 mono at 16 kHz, displays revised live turns, and keeps
  a recorded-audio fallback. Missing key: `503`; provider failure: `502`.

### 6. `POST /api/chat` (SSE stream)

- Purpose: send a user message, stream agent run. Body:

```json
{ "project_id": "uuid", "message_id": "optional stable id for retries", "message": "string (0-8000)", "resume": null, "attachment_ids": ["uuid"] }
```

- Resume after interrupt: `{ "project_id": "...", "message": "", "resume": [{ "type": "approve" }] }`
- A typed `message` while a card waits answers that card (spec 03 T5): a plain approval ("approve", "yes, save it",
  "looks good") resumes as `approve`; any other text as `reject` with the text as the change request. A `status`
  event says which. A message that names the brief ("approve the brief") approves its current revision through the
  same checks as `POST …/brief/approve`; the result is appended to the message for wizi in brackets.
- SSE events (`data: <json>\n\n`):
  - `{ "type": "token", "source": "main|<subagent>", "text": "..." }` — chat reply tokens
  - `{ "type": "status", "text": "..." }` — immediate readable progress
  - `{ "type": "heartbeat" }` — keepalive every five seconds while work is active
  - `{ "type": "step", "source": "...", "node": "model|tools|..." }` — graph node completions
  - `{ "type": "tool_call", "source": "...", "name": "...", "args_preview": "..." }`
  - `{ "type": "subagent", "status": "pending|running|complete", "name": "..." }`
  - `{ "type": "todos", "todos": [{ "content": "...", "status": "pending|in_progress|completed" }] }`
  - `{ "type": "interrupt", "interrupt_id": "...", "action_requests": [...], "review_configs": [...] }`
  - `{ "type": "doc_updated", "slug": "...", "title": "..." }`
  - `{ "type": "done", "thread_id": "..." }` and `{ "type": "error", "detail": "..." }`

### 6b. Brief and decisions

- `PUT /api/projects/{id}/brief` → `200 {status, revision, missing, brief}`. `brief.intake` is `idea` (default),
  `feature` or `cleanup`; it is never listed in `missing`. Any other value → `422`.
- `POST /api/projects/{id}/work-items` → `201` the item. `owner_type`: `stakeholder` (default), `default` or `repo`.
  `blocked_by`: IDs of existing items that must be resolved first; an unknown ID → `422`.
- `PATCH /api/projects/{id}/work-items/{item_id}` `{status, resolution}` → `200` the item (`basis: user_confirmed`).
- `GET /api/projects/{id}/quality` → includes `items` and `frontier`: the IDs of open items whose blockers are all
  resolved. A deferred blocker keeps its dependents off the frontier.
- In chat, wizi's `settle_decision` tool resolves an item only when the quoted `user_words` appear in the user's
  latest message (`basis: user_answered`, words kept in `answered_with`); repo-owned items are never settled this
  way.
- `GET /api/projects/{id}/questionnaire` → `200 text/markdown`, `<project-slug>-questions.md`: the frontier minus
  repo facts, one section per decision (`<!-- item:<id> -->`, detail, recommendation, empty **Answer:**).
- `POST /api/projects/{id}/questionnaire/answers` `{markdown}` → `200 {answered_by, settled, refused}`: each written
  answer settles its item (`basis: user_answered`; "yes" takes the proposal; the resolution names who answered).
  Unknown, settled and repo items are refused with a reason (spec 03 T6).

### 6c. Specs and the agent package

- `GET /api/projects/{id}/docs` also lists the spec files as `spec-<name>`: `spec-README` (the plan),
  `spec-agents` (the conventions), `spec-NN-<slug>`. `GET …/docs/spec-<name>` and its `/download` read them;
  any other name → `404`.
- `GET /api/projects/{id}/package` → `200 application/zip`, `<project-slug>-agent-package.zip`, to unzip at the
  repository root: `.claude/skills/build-<project-slug>/` (SKILL.md, `procedures/{task,check,refine}.md`,
  `scripts/check_scope.py`), `.ai/specs/`, `.ai/handover/<slug>.md` (the nine documents), `.ai/decisions.md`,
  `.ai/questions.md`, `.ai/README.md`, and the conventions as `AGENTS.md` + `CLAUDE.md` (intake `idea`) or
  `.ai/AGENTS.md` (`feature`, `cleanup`). `404` while no document exists. The skill also has
  `procedures/commit.md`: a branch per spec (`spec/<NN>-<name>`), one commit per task (`<NN>-T<n>: <title>`).
  A small change to an existing codebase may be one standalone ticket, `.ai/specs/ticket-<slug>.md` (one task),
  run like a spec: `/build-<project> task ticket-<slug> T1`.
- `GET /api/projects/{id}/package/checks` → `200 {blockers, warnings, findings: [{severity, file, message}]}`: tasks
  missing Do/Files/Read/Verify/Blocked by/Status, `Read:` links to missing files or headings, unknown blockers, plan
  links without a spec, a skill over 200 lines or naming requirement IDs, procedures without "Done when", unfilled
  placeholders. Warnings only: the download stays open (spec 06).
- `POST /api/projects/{id}/questions` `{markdown}` → `201 {created, existing}`: a package's `.ai/questions.md` back
  from the coding agent; each open `### Q<n>:` becomes a stakeholder decision citing its spec and task, its
  `affected_docs` from that task's `Read:`. Re-sending the same file creates nothing new.
- `GET …/docs/bundle` (the readable bundle) ends with `## Diagrams`: Mermaid build order (specs and cross-spec
  blockers) and decisions waiting on others, built from data when served (spec 05 T6).

### 7. Errors

- `404` unknown project; `422` validation; `409` thread busy (one run per project at a time);
  `500` → `{detail}`. Frontend MUST surface `error` events without crashing chat.

## Contract Rules

- Slug list/order MUST match §4 and the 9 `docs/*.md` contracts.
- SSE event `type` strings MUST NOT be renamed without a version bump.
- Frontend types in `src/api.ts` MUST mirror these models exactly.
