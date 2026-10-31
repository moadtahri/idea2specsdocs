# 02 Core skill and stages

## Why

Wizi's system prompt carries every rule for every stage at once: 13 rules (about 9,500 characters) plus the full
discovery playbook, on every call, in discovery and in drafting alike. Canyas learned that an agent follows the
rules of the step it is on more reliably when the app hands it that step's file, and that a rule written without
its *when* gets applied everywhere (lessons 4 and 5). Discovery also asks questions one batch at a time with no
order: nothing says which questions can be asked now and which depend on an answer still missing, and nothing
offers a recommended answer the user can accept with "yes".

## What

- A core skill, always in the system prompt, under 7,000 characters (a test enforces it): who wizi is, the stage
  map, and the rules that hold in every stage.
- One file per stage (discovery, drafting, review), added to the system message by the app from the project's
  state, never left to wizi to remember to read.
- An intake mode on the brief (`idea`, `feature`, `cleanup`), proposed by wizi from what was supplied and confirmed
  by the user with the brief. Feature and cleanup add their own file in every stage.
- Discovery in rounds: wizi maps open decisions as a tree, asks only the questions whose prerequisites are settled
  (at most three per round, the most consequential first), gives a recommended answer for each, and words each so
  "yes" accepts it. Facts in supplied material are wizi's to look up, never the user's to repeat.

## Context

**Relevant files**

- `backend/app/agent/prompts.py`: `ORCHESTRATOR_PROMPT` (to be replaced) and the specialist prompts (unchanged).
- `backend/app/agent/factory.py`: assembles the system prompt from the prompt, the project context and the
  discovery playbook.
- `backend/app/agent/skills/requirements-discovery/SKILL.md`: the current discovery playbook (pm-skills adaptation).
- `backend/app/agent/quality_skills.py`: loads packaged skills by name.
- `backend/app/quality_models.py`: `ProjectBrief`; `backend/app/quality_store.py`: `brief_state`.
- `backend/app/schemas.py`: `DOC_SLUGS`, the nine documents.
- `frontend/src/components/QualityPanel.tsx`, `frontend/src/api.ts`: the brief panel and its type.
- Port from: `../canyas-b2c-agents/Canyas_agentic_harness/backend/src/explainer_studio/director/stage_pin.py` and
  `skills/canyas-video-director/SKILL.md` (the core-plus-stages layout).
- Adapt from (MIT): mattpocock/skills `skills/productivity/grilling/SKILL.md`.

**Decisions already made**

- Stage from state, not from the model: `discovery` while the brief is not approved; `drafting` once it is and any
  of the nine documents is missing; `review` when all nine exist.
- The stage and mode files go into the system message, appended by middleware. Canyas pins them as conversation
  messages; here stages change about three times per project, so the cache cost is negligible, and the file can
  neither be folded away by compaction nor be mistaken for the user's words.
- The intake mode is a brief field with default `idea`, outside `BRIEF_FIELDS` (it never counts as missing).
- The specialists' prompts and the review playbooks stay as they are; spec 05 changes the outputs.
- Toolsets per stage are not built: `RequirementsGate` already hides drafting tools in discovery, and with ~20 tools
  (Canyas had 58) the saving is unmeasured (lesson 1). Spec 07 can revisit.
- Every current rule keeps its meaning; it moves to the stage where it applies. The one behaviour change is the
  discovery rounds.

## Constraints

**Must**

- Keep `deepagents` imports in `factory.py`.
- Credit the grilling adaptation in `SOURCES.md` and ship mattpocock/skills' MIT license beside pm-skills'.
- Write adapted procedures in our own words for this app's users (founders and product owners), not copies.

**Must not**

- Add dependencies.
- Change tools, the approval flow, the specialists or the nine documents.
- Ask the user to type approvals; the brief and documents keep their buttons (spec 03 changes that).

**Out of scope**

- Decision ownership on work items and questionnaires (spec 03); the repo-reader (spec 04).
- Evals over trials (spec 07). This spec ends with a live check, not a pass rate.

## Tasks

### T1: Core skill, stage files and mode files

**Do:** `wizi-core/SKILL.md` (identity, stage map, rules for every stage) and `stages/{discovery,drafting,review}.md`,
`modes/{feature,cleanup}.md`, moving each current rule to where it applies; discovery merges the pm-skills playbook
with the grilling rounds. Remove `requirements-discovery` (its content now lives in `stages/discovery.md`). Credit
sources and add the license.
**Files:** `backend/app/agent/skills/wizi-core/**`, `backend/app/agent/skills/requirements-discovery/SKILL.md`
(removed), `backend/app/agent/skills/SOURCES.md`, `backend/app/agent/skills/LICENSE.mattpocock-skills`
**Read:** `backend/app/agent/prompts.py`, Canyas `canyas-video-director/SKILL.md`, mattpocock `grilling/SKILL.md`
**Verify:** Manual: every one of the 13 current rules and 8 discovery steps is findable in the new files (checklist
in the task report).
**Status:** done, 2026-10-30. Rules 4, 7, 8, 12 → core; 1, 3, 5, 11 → core plus stages; 2, 9, 13 → drafting;
6 → review; 10 → modes/feature.md; discovery steps 1–8 → discovery.md §1–7. Core 4,117 characters.

### T2: Stage resolution and the stage middleware

**Do:** `stages.py` with `current_stage(project_id)`, `stage_files(stage, intake)` and `StageMiddleware`, which
appends the files to the system message before each model call; `factory.py` builds the system prompt from a
short identity plus the core skill; `quality_skills.py` loads the new files.
**Files:** `backend/app/agent/stages.py`, `backend/app/agent/factory.py`, `backend/app/agent/prompts.py`,
`backend/app/agent/quality_skills.py`, `backend/tests/test_stages.py`
**Verify:** `.venv-win/Scripts/python.exe -m pytest -q tests/test_stages.py`
**Status:** done, 2026-10-30 (`tests/test_stages.py`: 11 passed, including a real graph that sees the core skill
and the discovery stage in its system message)

### T3: Intake mode on the brief

**Do:** `intake` on `ProjectBrief` (`idea` default, `feature`, `cleanup`), described in `propose_project_brief`;
a select in the brief panel.
**Files:** `backend/app/quality_models.py`, `backend/app/agent/tools.py`, `frontend/src/api.ts`,
`frontend/src/components/QualityPanel.tsx`, `backend/tests/test_stages.py`
**Verify:** `.venv-win/Scripts/python.exe -m pytest -q` and `npm run build` in `frontend/`
**Status:** done, 2026-10-30 (96 passed; build passed in WSL, Node 22). Browser smoke scripts not run.

### T4: Live check and contract

**Do:** One real discovery turn on a new idea and one drafting turn after brief approval; note the outcome here.
Record the layout in the architecture doc.
**Files:** `docs/03-sad-architecture.md`, this spec
**Verify:** Manual: the discovery reply asks numbered questions with recommended answers (at most three) and
proposes a brief with an intake mode; the drafting turn pauses for a document approval.
**Status:** done, 2026-10-30, real Muse model. Discovery ("a small vet clinic in Lyon… no software yet"): three
numbered questions (appointment types, vet choice, bookable hours), each with "Recommended:" and why it matters,
ending "Reply **yes** to take every recommendation…"; brief saved as proposed, `intake: idea`, five areas still
missing and reported as incomplete. Drafting after approval: a todo plan, a founder-level explanation, then a pause
for `write_file /docs/prd.md`. No errors or warnings in the server log; project deleted. Seen, not in scope: text
wizi streams before and after a tool call is joined without a space ("online.Reading"); this predates spec 02.

## Done

- [x] `.venv-win/Scripts/python.exe -m pytest -q` passes: 96
- [x] `npm run build` in `frontend/` passes (WSL, Node 22)
- [x] The core skill is under 7,000 characters (test): 4,117
- [x] Live check passed (T4)
