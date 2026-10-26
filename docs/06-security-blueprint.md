# Security Blueprint — idea2specsdocs

- Status: APPROVED FOR BUILD
- Date: 2026-10-25

## 1. Threat Model (MVP)

Single-user local app, no auth. Main risks: prompt injection via chat steering doc writes,
XSS via rendered agent markdown, oversized payloads, secret leakage, dependency CVEs.

## 2. Controls (Binding)

- C1: Backend MUST enforce Pydantic limits (chat message ≤ 8000 chars, title ≤ 200, doc slug allowlist).
- C1b: Uploads MUST enforce 10 MB cap + content-type allowlist (text/md/json/csv, pdf, docx, audio);
  filenames sanitized to basename; served files NEVER executed.
- C2: Agent filesystem tools MUST be scoped to `projects/<project_id>/` via backend permissions;
  interrupt on any write outside scope.
- C3: Doc writes/overwrites REQUIRE HITL approval (`interrupt_on` write_file/edit_file); UI shows diff/args.
- C4: Frontend MUST render agent markdown with a sanitizer (no raw HTML passthrough).
- C5: CORS MUST allow only `http://localhost:5173` in dev; production origin via `CORS_ORIGINS` env.
- C6: No secrets in repo. `MODEL` + API keys via `.env` only. `.db` files git-ignored.
- C7: `uv lock` committed; frontend lockfile committed; audit before release.

## 3. Headers (Production)

- `X-Content-Type-Options: nosniff`, `frame-ancestors 'self'`, no inline scripts beyond Vite bundle.

## 4. Out of Scope for MVP

AuthN/Z, rate limiting (v0.2: slowapi or gateway), audit logging.
