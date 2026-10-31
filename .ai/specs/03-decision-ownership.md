# 03 Decision ownership and the decision map

## Why

Coding agents fill gaps with their own choices; this app exists to make those choices first, with the people who
own them. Today the decision register holds open items with a free-text owner and no order between them. Wizi
cannot tell which decisions the user can settle now and which wait on another, nor whether a decision is the
stakeholder's to make, an engineering default to confirm, or a fact to look up in the code. An answer the user
types in chat never reaches the register: only the card's buttons resolve an item, so the register goes stale while
the chat moves on. And the user has no view of the whole: what is decided, what can be decided now, what waits.

The wayfinder map (mattpocock/skills) shows the shape that works: decisions as a graph with "blocked by" edges, the
frontier (open and unblocked) highlighted, each node opening its question. Its users also report how it fails:
charting too much too early, and the agent answering its own questions.

## What

- Each work item says who settles it (`owner_type`: stakeholder, default, repo) and which items must be settled
  first (`blocked_by`).
- The quality state lists the frontier: open items whose blockers are all resolved.
- A typed answer settles an item through `settle_decision`, only when the user's own words are in their latest
  message.
- A decision map in the brief panel: decisions as a top-to-bottom graph, the frontier glowing, a click opening the
  item's card.

## Context

**Relevant files**

- `backend/app/quality_models.py`: `WorkItemInput`, `WorkItem`, `ItemResolution`.
- `backend/app/quality_store.py`: `propose_item`, `resolve_item`, `items`.
- `backend/app/quality.py`: `assessment` (the quality state the panel reads).
- `backend/app/agent/tools.py`: `propose_work_item`; `backend/app/agent/requirements.py`: the discovery allowlist.
- `backend/app/agent/skills/wizi-core/stages/discovery.md`, `SKILL.md`: how wizi uses the register.
- `frontend/src/components/QualityPanel.tsx`, `frontend/src/api.ts`, `frontend/src/styles.css`.
- Read: mattpocock/skills `skills/engineering/wayfinder/SKILL.md` and `docs/engineering/wayfinder.md`.

**Decisions already made**

- `owner_type` defaults to `stakeholder`; `blocked_by` holds IDs of items that already exist, so the graph cannot
  form a cycle (a blocker is always created first).
- A blocker counts as settled only when `resolved`. A deferred blocker keeps its dependents waiting.
- `settle_decision(item_id, user_words, resolution)`: `user_words` must appear, case- and space-insensitively, in
  the latest user message; a plain yes settles the item to its proposal. Recorded with `basis = "user_answered"`
  and the quoted words. Repo-owned items cannot be settled this way: facts are looked up, not voted on.
- Only the map's layout is computed in the browser: longest-path layers, top to bottom, no new dependency.
- Wizi records an item only once its question can be stated precisely (wayfinder's "fog or ticket" test); vaguer
  concerns stay in the brief's open questions.

## Constraints

**Must**

- Keep the existing card buttons and API working unchanged for items without the new fields.
- Show items by title, never by bare ID.

**Must not**

- Let wizi resolve an item without the user's words.
- Add dependencies.

**Out of scope**

- Typed words approving the brief or a document card (Canyas KH-12): a later task here, once this path has run.
- Questionnaires for stakeholders who are not in the chat (mattpocock `to-questionnaire`): a later task.

## Tasks

### T1: Ownership, blockers and the frontier

**Do:** `owner_type` and `blocked_by` on `WorkItemInput` (validated against existing items in `propose_item`);
`frontier(items)` in the store; `frontier` in the quality state; `propose_work_item` documents both fields.
**Files:** `backend/app/quality_models.py`, `backend/app/quality_store.py`, `backend/app/quality.py`,
`backend/app/agent/tools.py`, `backend/tests/test_decisions.py`
**Verify:** `.venv-win/Scripts/python.exe -m pytest -q tests/test_decisions.py`
**Status:** done, 2026-10-30

### T2: Settling a decision from the user's words

**Do:** `settle_decision` tool reading the latest user message from the run's state; allowed in discovery; the
discovery stage and core skill say when to record items, how to wire `blocked_by`, and to settle answered items.
**Files:** `backend/app/agent/tools.py`, `backend/app/quality_store.py`, `backend/app/quality_models.py`,
`backend/app/agent/factory.py`, `backend/app/agent/requirements.py`,
`backend/app/agent/skills/wizi-core/stages/discovery.md`, `backend/app/agent/skills/wizi-core/SKILL.md`,
`backend/tests/test_decisions.py`
**Verify:** `.venv-win/Scripts/python.exe -m pytest -q`
**Status:** done, 2026-10-30 (104 passed; a real graph run settles one item from the user's words and refuses another whose words were not in the message)

### T3: The decision map

**Do:** `DecisionMap.tsx`: layered SVG graph from `items` and `frontier`, frontier nodes glowing, resolved dim,
blocked outlined; clicking a node opens its card below the map. Placed in the brief panel above the list.
**Files:** `frontend/src/components/DecisionMap.tsx`, `frontend/src/components/QualityPanel.tsx`,
`frontend/src/api.ts`, `frontend/src/styles.css`
**Verify:** `npm run build` in `frontend/` (WSL); Manual: the map in a running app.
**Status:** done, 2026-10-31. Seen in the running app (browser pass from a Linux copy): the frontier glows, waiting
decisions sit under their blockers, a questionnaire's answers dim the settled ones and light the next. Animated at the
user's request: rows draw in, frontier nodes breathe and ripple, light flows along each arrow from a settled decision
into one it unlocked, stars twinkle; all of it off under prefers-reduced-motion (checked frame by frame).

### T4: Live check and contract

**Do:** A real discovery turn records items with `blocked_by`; answering "yes" settles the frontier items through
`settle_decision`; the API returns the next frontier. Record the change in the API and architecture docs.
**Files:** `docs/04-api-specification.md`, `docs/03-sad-architecture.md`, this spec
**Verify:** Manual: as described, with the server log clean.
**Status:** done, 2026-10-30, real Muse model. First attempts recorded only the round's questions (no edges, a flat map); moving "record the waiting questions with `blocked_by`" into the round procedure, with its when and why (Canyas lesson 5), fixed it in the next run: 2 frontier items and 2 waiting on "Appointment types and durations". Replying "yes" settled both frontier items (`answered_with: yes`), the waiting two became the frontier and were asked, and a new waiting item was recorded. Server log clean; projects deleted. One run each: spec 07 should measure the pass rate.

### T5: Typed approvals of the brief and document cards

**Do:** While a card waits, the composer stays open (typing and voice). The chat route reads the paused graph: a
message that is plainly an approval ("approve", "yes, save it", "looks good") resumes as the card's Approve; any
other message resumes as Request changes with the message as the change. A message that explicitly approves the
brief ("approve the brief") approves the current revision through `approve_brief`, whose checks still apply; the
outcome is noted for wizi in the message. A plain "yes" never approves the brief: in discovery it settles decisions.
The core skill drops "never in typed words" and says the app, not wizi, turns words into approvals.
**Files:** `backend/app/typed_approval.py`, `backend/app/main.py`, `backend/app/agent/skills/wizi-core/SKILL.md`,
`frontend/src/components/Chat.tsx`, `frontend/src/components/Composer.tsx`,
`frontend/src/components/Approvals.tsx`, `backend/tests/test_typed_approval.py`
**Verify:** `uv run pytest -q tests/test_typed_approval.py`; `npm run build`
**Blocked by:** T4
**Status:** done, 2026-10-30 (`tests/test_typed_approval.py`: 14 passed, a real graph through the chat route: typed
changes reject with the words, "looks good, thanks" saves; build passed)

### T6: Questionnaires for stakeholders outside the chat

**Do:** `GET /questionnaire` writes the decisions that can be settled now (the frontier, never repo facts) as a
Markdown file: one section per decision with its detail, the recommendation, and an empty **Answer:**, plus
**Answered by:**. `POST /questionnaire/answers` reads the filled file: each written answer settles its item through
`answer_item` (same guards as `settle_decision`; "yes" takes the proposal; the resolution names who answered).
Unknown, settled and repo items are refused with a reason. The decisions panel offers both; the core skill tells
wizi to suggest it for decisions that belong to someone outside the chat.
**Files:** `backend/app/questionnaire.py`, `backend/app/quality_store.py`, `backend/app/main.py`,
`backend/app/agent/skills/wizi-core/SKILL.md`, `frontend/src/components/QualityPanel.tsx`, `frontend/src/api.ts`,
`frontend/src/styles.css`, `backend/tests/test_questionnaire.py`
**Verify:** `uv run pytest -q tests/test_questionnaire.py`; `npm run build`
**Blocked by:** T4
**Status:** done, 2026-10-30 (4 passed; build passed)

## Done

- [x] `.venv-win/Scripts/python.exe -m pytest -q` passes: 104
- [x] `npm run build` in `frontend/` passes (2026-10-30, WSL)
- [x] Live check passed (T4)
