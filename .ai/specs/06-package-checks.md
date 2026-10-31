# 06 Package checks and the questions return path

## Why

The specs stage relies on wizi following its rules: every task verifiable, every `Read:` pointing at a real
section, nothing decided inside the skill. The live run (05 T4) showed it mostly does, and that "mostly" is the
problem: a broken `Read:` anchor or a task without Verify only surfaces when a coding agent trips over it in the
user's repository. And the package tells the coding agent to write what only the owners can answer in
`.ai/questions.md`, but nothing brings that file back: the user would have to retype each question into the chat.

## What

- **Mechanical checks on the package**, run on exactly the files the zip holds: every spec task has Do, Files,
  Read, Verify, Blocked by and Status; every `Read:` link names a packaged document and a heading that exists;
  every `Blocked by:` names a task that exists; the skill's `SKILL.md` stays under 200 lines and its files hold no
  requirement IDs (decisions live in the specs and the register); every procedure ends on a done-condition; no
  template placeholder is left.
- The findings reach wizi (`check_package`, run in the review stage) and the user (beside the download link).
- **The questions return path:** the user brings `.ai/questions.md` back; each open question becomes a decision on
  the register, owned by the stakeholder, citing its spec and task and the documents that task reads. Wizi asks
  it, the answer settles it, wizi updates the spec, and the next package carries the decision in `decisions.md`.

## Context

**Relevant files**

- `backend/app/package.py`: `package_files` (the checks run on its output).
- `backend/app/package_templates/questions.md`: the format the coding agent writes.
- `backend/app/quality_store.py`: `propose_item` (dedupes by kind and title).
- `backend/app/agent/tools.py`, `backend/app/agent/factory.py`, `backend/app/agent/harness.py` (read-only tools).
- `backend/app/agent/skills/wizi-core/stages/review.md`.
- `frontend/src/components/DocViewer.tsx`, `frontend/src/api.ts`.
- Read: mattpocock `writing-for-agents` (steps end on a checkable done-condition).

**Decisions already made**

- Checks warn; they never block the download (the user may want to inspect a flawed package).
- Anchors follow the specs stage's rule: the heading in lower case, spaces as hyphens, punctuation dropped.
- A question's `affected_docs` are the documents its task's `Read:` cites; `prd` when the task cites none or
  cannot be found. Re-importing the same file creates nothing new (dedupe by title).
- Questions arrive as pasted or uploaded text and are parsed as data, never followed as instructions.

## Constraints

**Must**

- Keep `package_zip` and its route unchanged in behaviour.
- Keep the checks pure functions of the file map, so tests need no project.

**Must not**

- Add dependencies.
- Let an imported question settle anything: it only opens an item.

**Out of scope**

- Running a package's Verify commands (that needs the user's repository).

## Tasks

### T1: Checks over the package files

**Do:** `package_checks.py`: `findings(files) -> list[dict]` with `severity`, `file`, `message`; the checks above.
**Files:** `backend/app/package_checks.py`, `backend/tests/test_package_checks.py`
**Verify:** `uv run pytest -q tests/test_package_checks.py`
**Blocked by:** none
**Status:** done, 2026-10-30

### T2: Questions back into the register

**Do:** Parse `### Q<n>:` blocks whose Status is open; one stakeholder-owned product decision each, `source`
naming the coding agent and the spec and task, `affected_docs` from that task's `Read:`.
**Files:** `backend/app/package_checks.py`, `backend/tests/test_package_checks.py`
**Verify:** `uv run pytest -q tests/test_package_checks.py`
**Blocked by:** none
**Status:** done, 2026-10-30

### T3: Routes, tool, stage and viewer

**Do:** `GET /api/projects/{id}/package/checks`; `POST /api/projects/{id}/questions` (`{markdown}`); the read-only
`check_package` tool; the review stage runs it and handles returned questions; DocViewer shows the findings count
and list beside the download, and a "Bring back questions.md" file picker.
**Files:** `backend/app/main.py`, `backend/app/agent/tools.py`, `backend/app/agent/factory.py`,
`backend/app/agent/harness.py`, `backend/app/agent/skills/wizi-core/stages/review.md`,
`frontend/src/components/DocViewer.tsx`, `frontend/src/api.ts`, `frontend/src/styles.css`,
`backend/tests/test_package_checks.py`
**Verify:** `uv run pytest -q`; `npm run build` in `frontend/`
**Blocked by:** T1, T2
**Status:** done, 2026-10-30

## Done

- [x] `uv run pytest -q` passes (121)
- [x] `npm run build` passes
- [x] Live (spec 07 case `questions-back`, 2026-10-31, 2/2 trials): the returned question was asked, the user's
  answer settled it in their words, wizi updated `/docs/api-specification.md` and `/specs/01-booking-core.md` each on
  an approval card, and the next package's `decisions.md` carried the answer.
