# Backend configuration

Run `WATCHFILES_FORCE_POLLING=true WATCHFILES_IGNORE_PERMISSION_DENIED=true uv run uvicorn app.main:app --reload --reload-dir app --port 8000` from this directory in WSL.
To load a local configuration file, add `--env-file .env` (copy `.env.example`).

API keys come only from the provided `AwsSecretManager` in `app/secrets.py`,
which uses the backend's normal AWS credentials and Secrets Manager in `us-west-2`.
The AWS identity needs `secretsmanager:GetSecretValue` for the configured secret.
Do not put API keys in frontend configuration.

By default, voice transcription reads `ASSEMBLYAI_API_KEY` and the chat model reads
`Muse_API_KEY_TEST` from the shared JSON secret `dev/AppAlpha/secrets`. Field lookup
is case-insensitive. `ASSEMBLYAI_SECRET_NAME`, `ASSEMBLYAI_SECRET_KEY`,
`MODEL_SECRET_NAME`, and `MODEL_SECRET_KEY` override these names.
There is no environment API-key fallback. Restart the backend after
changing configuration. Failed secret lookups are retried on the next recording.

Check key availability without displaying it:

```sh
uv run python -m scripts.check_transcription_secret
```

The microphone shows volume-responsive bars, a timer and a silence indicator.
For live transcription the browser requests `POST /api/transcribe/token`; the
backend reads the AssemblyAI key from AWS and mints a 60-second temporary token
with a six-minute session cap. The token response is never cached, and the
permanent API key stays on the server. The browser uses an AudioWorklet to resample
microphone audio to mono 16 kHz PCM16 and sends it directly to AssemblyAI's streaming
WebSocket. No WebSocket proxy changes are needed in Nginx.

Partial turns appear in a live preview and are replaced by revised text without
duplication. Stop flushes the final audio, terminates the streaming session, and
puts the transcript in the composer for editing before sending. Recording stops
automatically after five minutes. Cancelling startup or leaving the project closes
the microphone, audio nodes and socket.

If live transcription is unavailable or disconnects, the browser keeps a local
recording and posts the full audio to `/api/transcribe` when stopped. The backend uses AssemblyAI's
[upload API](https://www.assemblyai.com/docs/pre-recorded-audio/api-reference/files/upload)
and transcript submission/polling API with a two-minute processing deadline.

Chat shows an immediate activity status and elapsed time, with progress and
heartbeats while a request is active. Failed requests offer Resend (preserves text,
attachment IDs and message ID) or Delete (removes the failed exchange from the
current chat view; uploaded files and generated documents remain available).

## Existing projects and feature requests

Attach source files (or a source ZIP), existing handover documents, and a feature
request. Supply the repository revision when available. The agent compares current
behavior with the intended contracts, surfaces conflicts, and proposes updates to
affected documents with implementation tasks, requirement IDs, migration/rollback
steps and acceptance/regression checks. It does not modify the uploaded repository.

Uploads are limited to 10 MB each and 10 attachments per message. ZIPs are read as
text without extraction or execution: up to 5,000 entries, 20 MB expanded and 200
supported UTF-8 files. Dependency/build directories and environment files are
skipped, and the context reports skipped files. The chat includes a short preview;
the agent can read the full saved context inside the project's uploads directory.

Each document write pauses for **Approve & save** or **Request changes**.
`bundle-agent` assembles the implementation contracts with a manifest, content hash,
missing-document statuses and operating instructions. `bundle` derives a readable
overview using the configured model, cached until the source documents change.
Both are viewable and downloadable; generating the overview needs model access.

## Agent harness

Wizi and each specialist run with the middleware in `app/agent/harness.py`. All settings
are optional environment variables:

| Setting | Default | Effect |
|---|---|---|
| `AGENT_MAX_MODEL_CALLS` | 50 | Model calls per run; at the limit wizi stops and says "continue" resumes |
| `AGENT_MAX_TOOL_CALLS` | 50 | Tool calls per run; further calls come back as errors |
| `AGENT_MAX_TOOL_FAILURES` | 3 | Failures of one tool per run before it is refused |
| `AGENT_MODEL_RETRIES` | 2 | Retries for connection, timeout, rate-limit and server errors |
| `MODEL_FALLBACK_NAME` | unset | Second model on the same endpoint and key, tried when the first fails |

A tool that raises answers the agent with an error result instead of ending the turn,
and an identical failed call is refused. Document writes are never refused: the user
approved them. Credential and bad-request errors are not retried, so the chat still
reports them. Conversations compact past 80k tokens, keeping the last 24 messages;
the folded part is saved under the project's `conversation_history/`. The limits are
starting values, not measurements; spec 07's evals revisit them.

## Checks

```sh
uv run pytest
uv run ruff check app tests
```
