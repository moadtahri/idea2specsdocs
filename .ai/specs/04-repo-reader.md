# 04 The repo reader

## Why

Feature and cleanup projects start from uploaded source. Today a source ZIP becomes one concatenated text file
(`/uploads/<id>.context.txt`, up to 200 files) that wizi reads into its own context. That fills the context the
whole project depends on, gets folded away by compaction, and mixes what the code does with what wizi proposes. The
Canyas harness lesson applies: long reading runs in isolation and comes back as a short, cited report. The specs
stage also needs repo facts (real paths, the real test command) so `Files:` and `Verify:` start closer to the truth.

## What

- **A source tree:** a source ZIP is also unpacked, with the same filters as the snapshot (text source only, no
  dependencies, no `.env`, no traversal), to `/uploads/<id>/source/`, with `/uploads/<id>/source-index.md` listing
  each file and its line count. Nothing is executed.
- **`repo-reader`, a read-only specialist:** only the built-in file tools, writes denied by permission, its own
  limits. Given the source root and a question, it returns a report under 700 words in a fixed shape: stack, layout,
  entry points, data stores, integrations, tests (runner and command), conventions, the behaviour the question is
  about (each observed claim citing `path:line`, assumed ones marked), risks for the change, and what it could not
  tell.
- **Wizi delegates source reading** in the feature and cleanup modes, records repo facts as `repo` items, and uses
  the report's real paths and commands in specs. Cleanup mode asks the reader for the behaviour inventory that the
  `00-baseline` spec locks with tests.

## Context

**Relevant files**

- `backend/app/source_context.py`: the filters and the snapshot; `backend/app/main.py`: `upload_file`.
- `backend/app/agent/factory.py` (the only deepagents import: `FilesystemPermission`), `backend/app/agent/prompts.py`.
- `backend/app/agent/skills/wizi-core/SKILL.md`, `modes/feature.md`, `modes/cleanup.md`.
- deepagents `SubAgent`: `tools` replaces the inherited tools; `permissions` replaces the parent's rules.

**Decisions already made**

- The snapshot (`.context.txt`) stays for non-delegating reads and old projects; the tree is added beside it.
- Paths are re-checked when written: a resolved path outside `source/` is skipped, whatever the filter said.
- The reader's report is returned to wizi, not saved: wizi records what matters on the register.

## Constraints

**Must**

- Keep upload limits and filters exactly as they are.
- Keep `factory.py` the only module importing deepagents.

**Must not**

- Execute, install or import uploaded code.
- Give the reader the register tools or any write.

**Out of scope**

- Git history or revisions: the upload is a snapshot; the revision stays "unknown unless provided".

## Tasks

### T1: The source tree

**Do:** `source_files(raw)` in `source_context.py` returns the filtered path → text map; the snapshot uses it;
`write_source_tree(directory, files)` writes the tree and the index, skipping any resolved path outside it; the
upload route calls it for a ZIP and names the tree in the preview.
**Files:** `backend/app/source_context.py`, `backend/app/main.py`, `backend/tests/test_repo_reader.py`
**Verify:** `uv run pytest -q tests/test_repo_reader.py`
**Blocked by:** none
**Status:** done, 2026-10-30 (127 passed)

### T2: The repo-reader specialist

**Do:** `REPO_READER` prompt in `prompts.py`; `repo_reader()` in `factory.py` with `tools: []`, a write-deny
permission over `/**`, and the harness breakers; registered beside the domain specialists.
**Files:** `backend/app/agent/prompts.py`, `backend/app/agent/factory.py`, `backend/tests/test_repo_reader.py`
**Verify:** `uv run pytest -q tests/test_repo_reader.py`
**Blocked by:** none
**Status:** done, 2026-10-30 (127 passed)

### T3: Wizi delegates

**Do:** The core skill points source reading to `repo-reader`; the feature and cleanup mode files say when to call
it, what to ask, how to record repo facts, and that specs use its paths and commands.
**Files:** `backend/app/agent/skills/wizi-core/SKILL.md`, `backend/app/agent/skills/wizi-core/modes/feature.md`,
`backend/app/agent/skills/wizi-core/modes/cleanup.md`, `backend/app/agent/requirements.py` (found in T2's test: the
discovery gate refused every `task` call, and discovery is where the code must be read; it now lets `repo-reader`
through and still refuses the other specialists until the brief is approved)
**Verify:** `uv run pytest -q tests/test_stages.py`; live: a feature project with a source ZIP calls `repo-reader`
and its reply cites files.
**Blocked by:** T1, T2
**Status:** done, 2026-10-30 (127 passed)

## Done

- [x] `uv run pytest -q` passes (127)
- [x] Live (spec 07 runs, 2026-10-31): 2/2 trials delegate to `repo-reader`, 0 reads of the snapshot by wizi, the
  brief's intake proposed as `feature` 2/2; the reply used facts only the code shows in 1/2.
