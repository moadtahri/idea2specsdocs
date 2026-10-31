# 01 Harness resilience

## Why

One raising tool ends wizi's whole turn: LangChain turns bad arguments and validation errors into tool results, but
anything else a tool raises (`ValueError("No project is selected")`, a locked SQLite store) ends the run; a control
test with the breaker removed confirmed it. One model hiccup ends the turn too,
and nothing stops a loop of identical failing calls. Compaction waits until 170k tokens and then keeps only 6
messages, because the Muse Spark model exposes no context profile. The Canyas director harness solved each of these
on the same deepagents 0.7.32, with measurements behind the numbers.

## What

Wizi and every specialist run with:

- per-run limits on model and tool calls, ending with a plain message the user sees;
- a breaker that turns a raising tool into an error result and refuses a call that already failed;
- model retries with backoff, and an optional fallback model;
- compaction at 80k tokens that keeps the last 24 messages, clips old tool arguments first, and never leaves an
  empty summary.

## Context

**Relevant files**

- `backend/app/agent/factory.py`: builds the deep agent; the only module that imports `deepagents`.
- `backend/app/agent/requirements.py`: `RequirementsGate` hides tools until the brief is approved.
- `backend/app/main.py`: the SSE loop; forwards model tokens only (`mode == "messages"`).
- Port from (read-only, another repo): `../canyas-b2c-agents/Canyas_agentic_harness/backend/src/explainer_studio/director/breakers.py`
  and `agent.py` (`resilience`, `compaction`, `conversation_digest`); reasons in its
  `docs/reference/motion-video/lessons-learned.md`, lessons 2, 8 and 11.

**Decisions already made**

- A failed tool result is a `ToolMessage` with `status == "error"`. Kanya's JSON envelope is not used here.
- `write_file` and `edit_file` are never refused by the breaker: they run only after the user approved them.
- After retries, a model error is raised again, so `main.py` still tells the user what went wrong.
- The fallback model is used only when `MODEL_FALLBACK_NAME` is set (same endpoint and key).
- Limits per run: 50 model calls, 50 tool calls, 3 failures per tool; env overrides. These are not measured yet;
  spec 07 revisits them.
- Compaction: trigger 80k tokens, keep 24 messages, clip older tool arguments past 50k tokens to 2,000 characters,
  summarize the whole folded part, digest of the exchange when the summary comes back empty. Folded turns go to
  `/conversation_history/` in the project folder (deepagents' default path), where wizi can read them back.
- Messages the harness adds for the user carry `additional_kwargs["itos_source"] == "harness"`.

## Constraints

**Must**

- Keep `deepagents` imports in `factory.py`; LangChain-only middleware goes in a new `backend/app/agent/harness.py`.
- Give each specialist its own breaker instances.
- Keep `compact_conversation` available before brief approval (discovery chats with transcripts get long).

**Must not**

- Add dependencies.
- Change prompts, tools or the approval flow.
- Edit old history to save tokens (lesson 2).

**Out of scope**

- Showing compaction in the chat (log it for now).
- Stage pinning, toolsets per stage, evals (specs 02 and 07).

## Tasks

### T1: Breakers and resilience middleware

**Do:** `harness.py` with `breakers()` (model limit with a friendly ending, tool limit, `RepeatFailureBreaker`),
`resilience()` (retry on connection, timeout, rate-limit and server errors; optional fallback), and
`conversation_digest()`. Settings from env with the defaults above.
**Files:** `backend/app/agent/harness.py`, `backend/tests/test_harness.py`
**Read:** `breakers.py` and `agent.py` in the Canyas director (above)
**Verify:** `.venv-win/Scripts/python.exe -m pytest -q tests/test_harness.py`
**Status:** done, 2026-10-30 (19 passed)

### T2: Wire into the agent

**Do:** Add breakers and resilience to wizi and to every specialist; replace deepagents' summarization with the
compaction settings above (a subclass named `SummarizationMiddleware` that substitutes the digest for an empty
summary); add `compact_conversation`; allow it in `RequirementsGate`. Build the fallback model in `llm.py`.
**Files:** `backend/app/agent/factory.py`, `backend/app/agent/llm.py`, `backend/app/agent/requirements.py`,
`backend/tests/test_harness.py`
**Verify:** `.venv-win/Scripts/python.exe -m pytest -q` (all pass)
**Status:** done, 2026-10-30 (84 passed)

### T3: Show harness messages

**Do:** Forward an `AIMessage` tagged `itos_source == "harness"` from a main-graph update as chat text, so the
turn-limit message reaches the user.
**Files:** `backend/app/main.py`, `backend/tests/test_harness.py`
**Verify:** `.venv-win/Scripts/python.exe -m pytest -q tests/test_harness.py`
**Status:** done, 2026-10-30 (23 passed)

### T4: Record the contract

**Do:** Note the harness in the architecture doc and the backend README (settings and their defaults). Compose
passes each variable explicitly, so add the settings there too.
**Files:** `docs/03-sad-architecture.md`, `backend/README.md`, `backend/.env.example`, `compose.yaml`, `.env.example`
**Verify:** Manual: each env setting in `harness.py` and `llm.py` appears in both `.env.example` files and in
`compose.yaml` with its default; `docker compose config --quiet` passes.
**Status:** done, 2026-10-30; `docker compose config --quiet` passed 2026-10-31 in WSL, for `compose.yaml` alone and
with the `compose.aws.yaml` overlay (Docker 29.1.3)

## Done

- [x] `.venv-win/Scripts/python.exe -m pytest -q` passes: 85 (62 before this spec)
- [x] `.venv-win/Scripts/python.exe -m ruff check app tests` passes (2026-10-30: `known-first-party = ["app"]` in
  `pyproject.toml`, so WSL and Windows sort imports the same way; `tests/test_quality.py` fixed)
- [x] Manual: a chat turn in the running app still streams, pauses for a document approval and resumes. Run
  2026-10-30 against the real Muse model, key from Secrets Manager through `AwsSecretManager` (same class as Canyas
  `utils/secret_manager.py`): a temporary project with an approved brief; wizi paused for `write_file /docs/prd.md`,
  approval resumed and saved it; no errors or harness warnings in the server log; project deleted afterwards.
