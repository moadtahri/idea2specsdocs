# Runbook / On-Call Docs — idea2specsdocs

- Status: APPROVED FOR BUILD
- Date: 2026-10-25

## 1. Service Map

- `api`: FastAPI on :8000 — `GET /api/health`, `POST /api/specs:generate`.
- `web`: Vite dev on :5173 (dev) / nginx on :8080 (prod future).

## 2. Startup (dev, WSL zsh)

```zsh
cd ~/projects/idea2specsdocs/backend && uv run uvicorn app.main:app --reload --port 8000
cd ~/projects/idea2specsdocs/frontend && npm run dev
```

## 3. Triage

| Symptom | Check | Fix |
|---------|-------|-----|
| Frontend blank | `curl localhost:5173` | restart `npm run dev` |
| `Failed to fetch` in UI | `curl localhost:8000/api/health` | restart api; check port clash `ss -ltnp \| grep 8000` |
| 422 on valid input | compare payload to `04-api-specification.md` | fix field names/limits |
| Port in use | `ss -ltnp \| grep -E '8000\|5173'` | kill PID or change `--port` |

## 4. Logs

- Backend: uvicorn stdout. Frontend: browser console + Vite terminal.
- Prod (v0.2): `docker compose logs -f api web`.

## 5. Rollback

- MVP has no deploys to roll back. For v0.2: `git revert <sha>` + redeploy previous image tag.
- On-call: moadtahri (https://github.com/moadtahri). SLA: best-effort (side project).
