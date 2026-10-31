# 07 Behaviour evals

## Why

Every rule wizi follows has been checked live exactly once (02 T4, 03 T4, 05 T4). One run says a rule *can* hold,
not how often it does: 03 T4 needed a second prompt change before decisions got their edges, and 05 T4 found specs
choosing libraries the documents never named. The Canyas harness measures pass rates over several trials before and
after each change; without that, a prompt edit that fixes one case can quietly break another.

## What

A runner, `python -m evals.run`, that drives the running app over HTTP with the real model, a disposable project
per trial, and grades each trial with named checks:

| Case | Checks (each a pass rate) |
|---|---|
| `discovery` (02, 03) | asks at most three questions; no writes, todos or domain specialists; uses the supplied vertical; records decisions with at least one waiting on another; a "yes" settles frontier items from the user's words and settles nothing else |
| `specs` (05, 06) | after an approval the next spec card comes without "continue"; no spec names a library, format or tool the documents and register do not; the package has no check blockers; the stage reaches review |
| `questions-back` (06) | wizi asks the question a coding agent sent back; the answer settles it in the user's words; the spec is updated on an approval card; the next package's `decisions.md` has the answer |
| `repo-reader` (04) | wizi delegates to `repo-reader`; never reads the source snapshot itself; its reply uses facts only the code shows; the proposed brief's intake is `feature` |

Results go to `backend/evals/results/<timestamp>.json`; `--compare <file>` prints each check's change. Graders are
pure functions over a recorded trial, so they are unit-tested without a model.

## Context

**Relevant files**

- `backend/scripts/check_discovery.py` (the first live check), the previous live-check script's flow (seed nine
  documents, approve the brief, resume with approvals).
- The chat SSE events (`backend/app/main.py`); the checkpoint (`store.checkpoint_path`), read for full tool calls.
- `backend/app/package_checks.py` (via `GET /package/checks`).

**Decisions already made**

- Runs against a server on the same host (it seeds documents and reads checkpoints from `store.PROJECTS_DIR`), and
  always deletes its projects.
- Trials default to 3; a check counts only trials that reached it (a trial that errors early is reported apart).
- The eval auto-approves cards and answers wizi's questions with one fixed "yes, go with your recommendations".

## Constraints

**Must**

- Never print secrets; print event summaries only.
- Keep graders independent of wording where possible: tools, files and the register first, text last.

**Must not**

- Add dependencies (`httpx` and `langgraph` are already there).
- Run in `pytest -q`: the unit tests cover the graders only.

**Out of scope**

- CI scheduling of live evals (cost); a dashboard.

## Tasks

### T1: Runner, cases and graders

**Do:** `evals/client.py` (chat stream, approvals, checkpoint read), `evals/cases.py` (setup, steps and checks per
case), `evals/fixtures.py` (vet brief and documents, a small source ZIP), `evals/run.py` (trials, results, compare).
**Files:** `backend/evals/__init__.py`, `backend/evals/client.py`, `backend/evals/cases.py`,
`backend/evals/fixtures.py`, `backend/evals/run.py`, `backend/tests/test_evals.py`, `.gitignore`
**Verify:** `uv run pytest -q tests/test_evals.py`
**Blocked by:** none
**Status:** done, 2026-10-31 (10 passed). The first live run found two grader bugs, now fixed and tested: the
checkpoint's latest snapshot holds no `messages` channel (calls are gathered from each step's writes), and graders
read reply text cut to 400 characters (only the saved results are cut now).

### T2: First baseline

**Do:** Run every case against the real model and record the baseline in this spec.
**Files:** this spec
**Verify:** Manual: `uv run python -m evals.run --trials 2` completes; results file written; projects deleted.
**Blocked by:** T1
**Status:** done, 2026-10-31 (below)

## Done

- [x] `uv run pytest -q` passes (161)
- [x] A baseline is recorded below

## Baseline

Real Muse model, 2026-10-31. Each run fixed what the one before found.

| Case: check | Run 1 (1 trial) | Run 2 (2 trials) | Run 3 (specs, 2 trials) |
|---|---|---|---|
| discovery: at most three questions | 1/1 | 2/2 | |
| discovery: no writes or specialists | 1/1 | 2/2 | |
| discovery: uses supplied context | 1/1 | 2/2 | |
| discovery: decisions have edges | 0/1 | 2/2 | |
| discovery: yes settles only the frontier | 0/1 | 2/2 | |
| repo-reader: delegates | 0/1 (grader bug) | 2/2 | |
| repo-reader: never reads the source itself | 1/1 | 2/2 | |
| repo-reader: uses facts from the code | 0/1 | 1/2 | |
| repo-reader: intake is feature | n/a | 2/2 | |
| specs: continues after approval | 0/1 | 1/2 | 2/2 |
| specs: decides nothing new | 0/1 (toml, requirements.txt, uvicorn) | 0/2 (psycopg; toml) | 1/2 (httpx) |
| specs: package has no blockers | 1/1 | 1/2 | 2/2 |
| specs: reaches review | 1/1 | 1/2 | 2/2 |

**What the runs found and changed**

- Run 1: every `propose_work_item` failed. The tool took one `item` dict; the model sent the fields flat, lists as
  JSON text, or dropped required fields (likely the same five silent failures as 05 T4). The tool now takes flat
  typed arguments and accepts a list as JSON text. Failing to record, wizi wrote `/tmp/test-tool.md` to "try another
  way": writes are now limited to `/docs/` and `/specs/`.
- Run 2: specs named plumbing nobody chose; the specs-stage rule now names the dependency file, the app server and
  the linter as decisions. One trial lost three specs: writes to `/.ai/specs/…` matched no permission (`**` skips
  dot folders) and, with the blanket approval rule removed, saved with no card. Fixed: every write pauses on a card
  again, and the deny rule names dot folders (tested).
- Run 4 (3 trials each): repo-reader held (delegates 3/3, code facts 3/3) but wizi read the snapshot once (2/3);
  specs collapsed: continues 1/3, reaches review 0/3. After each approval wizi often ended the turn asking the user to
  approve the card they had just approved. Fixed: right after a spec save the app adds one line, pinned when it
  applies: what was saved, that no card waits, and the next file to write now. Source uploads now point wizi only at
  the tree for `repo-reader`, not the snapshot.
- Run 5 (3 trials each, after those fixes): repo-reader 3/3 on every check; specs: continues 3/3, package without
  blockers 3/3, reaches review 3/3, decides nothing new 2/3 (`toml` once).
- `questions-back` (2 trials): 2/2 on every check.
- Browser pass, 2026-10-31: after a typed "looks good, thanks" saved the PRD, wizi still said the draft was waiting on
  its card. The pinned line now follows any approved save, documents included: what was saved and that no card waits
  (specs also get the next file to write). The six smoke scripts pass again; three had fakes older than the brief
  panel and one stopped a voice note after 0 ms.
- Runs 6-11 (specs, 3 trials each), 2026-10-31. The grader now prints the spec line behind each flag. Read
  that way, `httpx` (FastAPI's test client), TOML (ruff's settings file) and YAML (GitHub Actions, Compose) were
  parts of confirmed choices, not new ones: the grader accepts them when the choice that needs them is named, and the
  rule tells wizi to say so. `psycopg` once and `requirements.txt` once were genuine misses. Stops after an approval
  were traced one by one: the pinned line looked only at the last tool result (a step with settle calls then a
  write), then only at the step right after the save (wizi updated its to-dos first), and wizi sometimes ignored it.
  It is now enforced: when wizi ends a specs-stage turn with specs left, no card waiting and no decision open, the
  app sends it back (at most twice since the last save or user message; the second time "describing it is not
  writing it"). The independent review now decodes JSON-text arguments and logs which fields failed.
- Run 11 (after all of it): specs 3/3 on every check, 18 of 18 approvals led straight to the next card.
- Still open: a spec occasionally uses another task-heading format; the package checks catch it as a blocker and the
  review stage repairs it.
