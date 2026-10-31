# itos

Chat-first app: brainstorm a software idea with **wizi** and its specialist team
(planner, architect, API designer, data modeler, security, DevOps, QA) and get the
**9 handover documents** as contracts for implementing agents — remembered per-project in
local **SQLite** so you can resume, update, and ask follow-ups.

| Phase | Documents |
|---|---|
| Planning | PRD, Technical Spike, SAD/Architecture |
| Development | API Specification, Database Schema, Security Blueprint |
| Deployment & Live | DevOps IaC Spec, QA Test Plan, Runbook |

## Stack

- **Backend:** FastAPI + `uv` venv (project-specific `backend/.venv`, Python 3.12),
  `deepagents` + `langgraph` + `langgraph-checkpoint-sqlite`, SSE streaming, HITL approvals.
- **Frontend:** React + TS + Vite (Node 22), streaming chat + approvals + doc viewer.
- **Dev env:** WSL Ubuntu 24.04, zsh.

## Run with Docker Compose

From the repository root in WSL, start itos with your local AWS profile available
to wizi and AssemblyAI transcription:

```sh
docker compose -f compose.yaml -f compose.aws.yaml up --build -d --wait
```

Open **http://localhost:8080**. The same origin serves the frontend and `/api`.
The API stays on the internal Docker network. Docker images run without a reload
watcher; rebuild after editing application code.

`compose.aws.yaml` mounts `~/.aws` read-only into the API container. Set
`AWS_CONFIG_DIR` to another absolute credential directory if needed, and
`AWS_PROFILE` to select a profile. The API image runs as UID 1000; mounted profile
files must be readable by that UID. Cloud deployments using an IAM role or exported
AWS credential variables can use the base file alone:

```sh
docker compose up --build -d --wait
```

Copy the root `.env.example` to `.env` to customize `APP_PORT` (8080 by default),
model settings and secret names. API keys are fetched from AWS Secrets Manager at
runtime and are excluded from both images.

SQLite state, summaries, uploads and generated documents persist in the `itos-data`
and `itos-projects` named volumes. The Compose stack has its own data; existing
non-container `backend/data` and `backend/projects` directories are not imported.
`docker compose down` stops the stack while retaining those volumes.

```sh
docker compose ps
docker compose logs -f api web
docker compose --profile test run --rm --build api-tests
```

The API health check is available at http://localhost:8080/api/health. Nginx proxies
SSE without buffering so wizi's progress and replies stream while it works. Project
Rename and Delete controls are beside the dropdown; Delete immediately stops that
project's work and removes its documents, uploads, checkpoints and database records.

To repeat the container smoke checks, including a real AWS-backed wizi request and
data persistence across recreation:

```sh
docker compose exec -T api python -m scripts.check_compose --seed
docker compose -f compose.yaml -f compose.aws.yaml up -d --force-recreate --wait
docker compose exec -T api python -m scripts.check_compose --verify --live --delete-active
docker compose exec -T api python -m scripts.check_compose --cleanup
```

These checks create and remove their own temporary project data.

## Run the backend (WSL zsh)

```zsh
cd backend
cp .env.example .env   # configure model and AWS secret names
WATCHFILES_FORCE_POLLING=true WATCHFILES_IGNORE_PERMISSION_DENIED=true uv run uvicorn app.main:app --env-file .env --reload --reload-dir app --port 8000
```

Health: http://localhost:8000/api/health — interactive docs: http://localhost:8000/docs

## Run the frontend (WSL zsh)

```zsh
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 (calls `/api`, proxied to the backend).

## How it works

1. Create a project → backed by `backend/data/<project_id>.db` (checkpoints = memory)
   and `backend/projects/<project_id>/docs/*.md` (the 9 docs).
2. Wizi reads your description, recording and files, establishes the app vertical and
   service, then asks at most three missing, service-specific questions per turn.
3. Use **Review project brief** to edit the shared brief, then **Approve brief & plan
   bundle**. Research, specialist planning, bundle TODOs and document writes wait for
   this approval. A changed brief needs approval again. Simple tools stay proportional.
4. Chat streams readable replies and progress. Document writes pause for **Approve &
   save** or **Request changes**. Decisions, proposals and deployment inputs are
   recorded separately with owners, affected documents and the phase they block.
5. Run the independent review from the brief panel. Mechanical checks and a separate
   model review identify missing contracts, undefined IDs, inconsistent requirements,
   unmapped security controls and unsupported claims, with validated document citations.
6. Reopen the project later — brief, decisions, conversation and documents persist.
   Download drafts at any time as an agent bundle or readable companion, including
   unresolved findings and readiness. Changing documents, decisions or evidence
   invalidates previous reviews and the readable cache.

Readiness distinguishes a reviewed implementation specification from implementation
verification and production readiness. The latter states require uploaded results,
explicit user attestation, matching specification/code revisions, coverage IDs and
the selected deployment environment. Itos does not run uploaded project code or
independently certify the uploaded results. A written spike plan is not a passed spike.

The application-owned discovery and review playbooks live in
`backend/app/agent/skills/`. Discovery adapts the MIT-licensed
[pm-skills interview and PRD procedures](https://github.com/phuryn/pm-skills);
source attribution and the license ship alongside the playbooks. No IDE skill
installation or runtime skill download is required.

For an existing project, attach source files or a source ZIP, the existing handover
docs, and the requested feature. The agent specifies the change in affected docs,
including implementation tasks and acceptance checks. The source establishes current
behavior; the handover docs establish intended contracts. Conflicts are surfaced for
review. Uploaded repositories are analyzed as text, not executed or modified.

Chat and document previews render Markdown with boxed code callouts. Voice messages
show a microphone level meter and live transcription. Stop finalizes the text in
the composer for review; a recorded-audio fallback handles streaming failures.
AssemblyAI transcription reads `ASSEMBLYAI_API_KEY` through the supplied AWS Secrets Manager module;
see [backend setup](backend/README.md) for secret names and AWS configuration.

## Contracts

`docs/` holds the 9 binding contracts (01-prd → 09-runbook) plus architecture/API/DB/security specs.
