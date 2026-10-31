# 08 The conversation survives a reload

## Why

The chat starts empty whenever a project is opened: in another browser, after a reload, or after switching projects.
The project name, the brief, the decisions and the documents are on the server, and wizi remembers the conversation
through its checkpoints, but the screen never asks for the earlier messages. A waiting approval card disappears too,
so the user cannot approve it after a reload. The checkpoints cannot serve as the transcript: compaction replaces
old turns with a summary, and they hold tool traffic the user never saw.

## What

- The server keeps a transcript per project: each user message (with its attachment names) and each wizi reply, in
  order, as the user saw them; plus the approval card that is waiting and the latest to-do list.
- `GET /api/projects/{id}/history` returns them; the chat loads it whenever a project opens.
- A message is recorded when its run finishes (done or waiting on a card), so a failed request the user deletes or
  resends is never recorded twice.

## Context

**Relevant files**

- `backend/app/store.py` (SQLite registry), `backend/app/main.py` (the chat stream), `frontend/src/components/Chat.tsx`,
  `frontend/src/api.ts`.

**Decisions already made**

- Two tables in `app.db`: `chat_messages` (one row per message, unique by project and message id) and `chat_state`
  (the waiting card and the to-dos). Deleting a project deletes its rows.
- An approval sent from a card is recorded as the card's summary ("✅ Approved: PRD"); a typed answer as typed.
- Projects created before this spec have no transcript; their screen starts empty as before.

## Constraints

**Must:** keep the chat stream's events unchanged; record only what the user saw (never tool calls or app notes).
**Must not:** add dependencies; store secrets or document bodies in the transcript.

## Tasks

### T1: Transcript store, route and loading

**Do:** The two tables and their functions in `store.py`; the chat route records the user message and wizi's reply
when a run finishes, the waiting card on an interrupt (cleared by a run that ends without one), and the latest
to-dos; `GET /history`; `Chat.tsx` loads it on open.
**Files:** `backend/app/store.py`, `backend/app/main.py`, `frontend/src/api.ts`, `frontend/src/components/Chat.tsx`,
`backend/tests/test_history.py`
**Verify:** `uv run pytest -q tests/test_history.py`; `npm run build`; Manual: a conversation shows again after a
reload in another browser, including a waiting card.
**Blocked by:** none
**Status:** done, 2026-10-31 (179 passed; build passed)

## Done

- [x] `uv run pytest -q` passes (179)
- [x] Manual check in the running app (Docker): a real conversation in one browser session showed identically in a
  second session with no shared storage. Also fixed on the way: each of wizi's steps now starts a new paragraph
  ("…for your salon.Working out…" ran together, live and in the transcript).
