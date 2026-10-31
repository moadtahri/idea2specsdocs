# 05 The agent package

## Why

A coding agent receives one Markdown file holding all nine documents. It has no task to start from, no file list, no
check to run, no conventions file, and no way to send a question back. Everything is read in full for every task.
That is the contract a spec-driven workflow starts from, not the workflow itself: the agent still decides how to
split the work, in what order, and when it is done.

## What

- **A specs stage** after the nine documents: wizi writes a spec plan, the project conventions, and one spec per
  slice of work, each on the usual approval card.
- **A package**, downloadable as a zip, that drops into the user's repository:

```text
AGENTS.md, CLAUDE.md            ← conventions (idea mode); in feature/cleanup mode under .ai/ with merge notes
.claude/skills/<project>/
  SKILL.md                      ← the loop, the rules, the document map (generated)
  procedures/task.md            ← run one task
  procedures/check.md           ← check a diff against its task (standards and spec)
  procedures/refine.md          ← fill Files and Verify against the real repo
  procedures/commit.md          ← one commit per task, on the spec's branch, when the user asks
  scripts/check_scope.py        ← changed files vs the task's Files; new dependencies
.ai/specs/README.md             ← the spec plan: order and what each delivers
.ai/specs/NN-<slug>.md          ← Why / What / Context / Constraints / Tasks (Do, Files, Read, Verify, Blocked by)
.ai/handover/<slug>.md          ← the nine documents, read only through a task's Read:
.ai/decisions.md                ← the decision register as an index
.ai/questions.md                ← where the coding agent writes what only a stakeholder can answer
```

- The nine documents and the single-file agent bundle stay as they are (decided 2026-10-30: keep, add the package).

## Context

**Relevant files**

- `backend/app/agent/stages.py`, `backend/app/agent/skills/wizi-core/` (stage map and stage files).
- `backend/app/store.py`: `list_docs`, `read_doc`, `agent_bundle_markdown`; `backend/app/main.py`: doc routes.
- `backend/app/quality_store.py`: `items`, for `decisions.md`.
- `frontend/src/components/DocViewer.tsx`: document list and downloads.
- Read: `.ai/specs/README.md` (borrowed practice), Canyas `canyas-video-director/SKILL.md` (core plus stage files),
  mattpocock `writing-for-agents`, `to-tickets`, `code-review`; Owain Lewis `resources/commands/{spec,task}.md`.

**Decisions already made**

- Spec files live in the project folder under `specs/`: `README.md` (the plan), `agents.md` (conventions),
  `NN-<slug>.md`. The stage is `specs` once all nine documents exist and until the plan, the conventions and every
  spec the plan links exist; then `review`.
- Paths inside specs are the package's paths: `.ai/handover/<slug>.md#<heading-anchor>` for `Read:`.
- Every spec write pauses on the approval card (decided 2026-10-30).
- The idea mode's first spec is `00-foundation` (scaffold, test runner, CI so later Verify commands are real); the
  cleanup mode's is `00-baseline` (tests that record current behaviour); the feature mode starts at `01`.
- `Files:` are planned paths: the package's `refine` procedure checks them against the real repo before a task runs.
- The skill's `SKILL.md`, procedures, script and `questions.md` are fixed templates filled with project values;
  only the specs, the plan and the conventions are written by the model.
- Spec files show in the document viewer as `spec-<name>`.

## Constraints

**Must**

- Keep the nine documents, the agent bundle and the readable bundle working unchanged.
- Keep `check_scope.py` standard-library Python.
- Never put a decision in the skill: it points to the specs and the register.

**Must not**

- Add dependencies.
- Let a spec decide something the documents or the register leave open: wizi records a work item and asks instead.

**Out of scope**

- Mechanical checks on the package (spec 06).

## Tasks

### T1: The specs stage

**Do:** `specs.py` (plan parsing, missing files); the `specs` stage in `stages.py`; `stages/specs.md` with the spec
format and rules; the stage row in the core skill.
**Files:** `backend/app/specs.py`, `backend/app/agent/stages.py`, `backend/app/agent/quality_skills.py`,
`backend/app/agent/skills/wizi-core/stages/specs.md`, `backend/app/agent/skills/wizi-core/SKILL.md`,
`backend/tests/test_package.py`
**Verify:** `.venv-win/Scripts/python.exe -m pytest -q tests/test_package.py tests/test_stages.py`
**Status:** done, 2026-10-30

### T2: Package templates and assembly

**Do:** `package_templates/` (SKILL.md, three procedures, `check_scope.py`, `questions.md`) and `package.py`, which
builds the zip from the templates, the specs, the nine documents and the register.
**Files:** `backend/app/package.py`, `backend/app/package_templates/**`, `backend/tests/test_package.py`
**Verify:** `.venv-win/Scripts/python.exe -m pytest -q tests/test_package.py`; `check_scope.py` runs against a temp
git repo in a test.
**Status:** done, 2026-10-30 (check_scope.py: in scope → 0; a stray file and a manifest outside Files → 1; an unknown task → 2)

### T3: Routes and viewer

**Do:** `GET /api/projects/{id}/package` (zip); spec files in the document list and viewer; a "Download agent
package" link.
**Files:** `backend/app/main.py`, `backend/app/store.py`, `frontend/src/components/DocViewer.tsx`,
`backend/tests/test_package.py`
**Verify:** `.venv-win/Scripts/python.exe -m pytest -q`; `npm run build` in `frontend/` (WSL)
**Status:** done, 2026-10-30 (backend 112 passed; `npm run build` passed in WSL)

### T4: Live check and contract

**Do:** A project with an approved brief and nine short documents: a real specs-stage turn writes the plan, the
conventions and the first spec on approval cards; the package downloads and unzips with every file. Record the
change in the API and architecture docs.
**Files:** `docs/03-sad-architecture.md`, `docs/04-api-specification.md`, this spec
**Verify:** Manual: as described; server log clean.
**Status:** done, 2026-10-30, real Muse model, seeded with nine short vet-booking documents. Before writing any spec, wizi found four real gaps in them (no move API, receptionist without accounts, no time-off table, email undefined), refused to invent, and asked; its first attempts to record them failed validation five times, unlogged (the breaker now logs and counts invalid arguments); recorded on the second try; the user's typed answers settled all four. Then, one approval card each: the plan (00 foundation → 04 launch readiness), the conventions, and five specs; stage moved to review. The package downloaded with 25 files; specs carry Files, `Read:` anchors that exist, Verify naming TC IDs, cross-spec `Blocked by` (01-T2). Seen: wizi stops after each approved file and needs "continue"; and the specs picked engineering defaults the documents never named (SQLAlchemy, a YAML hours file whose library no spec names, requirements.txt). Rule 1 of `stages/specs.md` now names that case explicitly; not re-checked live yet. Project deleted.

### T7: Git in the coding agent's loop

**Do:** The package skill works with git: `task` starts only from a clean tree on the spec's branch
(`spec/<NN>-<name>`, created from the default branch), and never commits; a new `commit` procedure stages only the
task's Files and the spec and commits `<NN>-T<n>: <task title>` with the requirement IDs and the Verify result in the
body, only when the user asks; never push, amend or skip hooks. The SKILL.md loop, its rules and `.ai/README.md`
name the step.
**Files:** `backend/app/package.py`, `backend/app/package_templates/SKILL.md`,
`backend/app/package_templates/procedures/task.md`, `backend/app/package_templates/procedures/commit.md`,
`backend/tests/test_package.py`
**Verify:** `uv run pytest -q tests/test_package.py` (WSL)
**Status:** done, 2026-10-30 (113 passed)

### T8: Keep writing after an approved spec

**Do:** In the specs stage the app adds, after the stage file, the files still to write (read from disk each call),
and the stage file tells wizi to write the next one in the same turn after an approval, stopping only when none is
left, at an unsettled decision, or at the work limit (decided 2026-10-30: yes for specs; documents still pause).
**Files:** `backend/app/agent/stages.py`, `backend/app/agent/skills/wizi-core/stages/specs.md`,
`backend/tests/test_package.py`
**Verify:** `uv run pytest -q tests/test_package.py tests/test_stages.py`; live: approving one spec file leads
straight to the next card.
**Status:** done, 2026-10-30 (113 passed); live 2026-10-31: 11/11 approvals with specs left led to the next card or a
question (spec 07, run 3)

### T5: Package checks (spec 06)

### T6: Human bundle with Mermaid diagrams

**Do:** The readable bundle ends with diagrams built from structured data, never by the model: the build order
(specs, arrows from cross-spec `Blocked by:`) and the decisions that wait on others (register edges, settled green,
open amber). Added when served, not cached, so a new spec or decision shows at once. The app draws any Mermaid block
with `mermaid` 11.17.2 (approved 2026-10-31), loaded only when a diagram is on screen, strict security level, dark
theme; if it cannot draw one, the source shows.
**Files:** `backend/app/diagrams.py`, `backend/app/main.py`, `frontend/src/components/Markdown.tsx`,
`frontend/src/components/MermaidDiagram.tsx`, `frontend/package.json`, `backend/tests/test_diagrams.py`
**Verify:** `uv run pytest -q tests/test_diagrams.py`; `npm run build`
**Blocked by:** none
**Status:** done, 2026-10-31 (4 passed; build passed; drawn in the running app: 3 nodes, arrows visible, no page
errors)

## Done

- [x] `.venv-win/Scripts/python.exe -m pytest -q` passes: 112
- [x] `npm run build` in `frontend/` passes
- [x] Live check passed (T4), with the two findings above
