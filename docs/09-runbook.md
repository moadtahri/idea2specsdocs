# Runbook / On-Call Docs — idea2specsdocs

- Status: APPROVED FOR BUILD
- Date: 2026-10-25

## 1. Service Map

- `api`: FastAPI on :8000 — `/api/health`, `/api/projects`, `/api/chat` (SSE),
  `/api/projects/{id}/uploads`, `/api/transcribe`, `/api/projects/{id}/docs`.
- `web`: Vite dev on :5173, proxies `/api` → `http://localhost:8000`.

## 2. Startup (dev, WSL zsh — two terminals)

Terminal 1 — backend (project venv, foreground so logs stream):

```zsh
export PATH="$HOME/.local/bin:$HOME/.local/node/bin:$PATH"
cd /mnt/c/users/moadt/projects/idea2specsdocs/backend
uv run uvicorn app.main:app --reload --port 8000 --log-level info
```

Terminal 2 — frontend:

```zsh
export PATH="$HOME/.local/bin:$HOME/.local/node/bin:$PATH"
cd /mnt/c/users/moadt/projects/idea2specsdocs/frontend
npm run dev
```

Open http://localhost:5173. Health: http://localhost:8000/api/health.

## 3. Triage

| Symptom | Check | Fix |
|---------|-------|-----|
| Frontend blank | `curl localhost:5173` | restart `npm run dev` |
| `Failed to fetch` in UI | `curl localhost:8000/api/health` | restart api; check port clash `ss -ltnp \| grep 8000` |
| 422 on valid input | compare payload to `04-api-specification.md` | fix field names/limits |
| Port in use | `ss -ltnp \| grep -E '8000\|5173'` | kill PID or change `--port` |

## 4. Logs — what each console shows

Backend terminal (`idea2specs.chat` logger, one line per event):

```text
[user-id] user: <first 200 chars of message>
[user-id] 💭 <thinking/reasoning chunk, 300 chars>
[user-id] ⚙ <tool-name> <args preview>     # agent is calling a tool
[user-id] ✔ <tool-name> → <result preview> # tool finished
[user-id] ▸ step: <graph node>              # model/tools/todos node ran
[user-id] ☑ todos 3/7                      # plan progress snapshot
[user-id] 📎 upload notes.md (text/markdown, 22 bytes)
[user-id] ⏸ interrupt: awaiting approval for ['write_file']
[user-id] done
```

Plus uvicorn access lines: `127.0.0.1:port - "POST /api/chat HTTP/1.1" 200 OK`.

Frontend terminal (Vite): HMR updates, compile errors, request proxying.
Browser DevTools (F12): Console tab (React errors), Network tab → click a
`/api/chat` request → EventStream sub-tab shows raw SSE tokens live.

- Prod (v0.2): `docker compose logs -f api web`.

## 5. Rollback

- MVP has no deploys to roll back. For v0.2: `git revert <sha>` + redeploy previous image tag.
- On-call: moadtahri (https://github.com/moadtahri). SLA: best-effort (side project).
