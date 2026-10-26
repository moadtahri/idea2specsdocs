# QA Test Plan — idea2specsdocs

- Status: APPROVED FOR BUILD
- Date: 2026-10-25

## 1. Strategy

- Backend: `pytest` unit tests for `generate_spec` + API contract tests via `httpx`/`TestClient`.
- Frontend: `vitest` + React Testing Library for form states; `tsc --noEmit` as gate.
- Manual: smoke checklist below on every release.

## 2. Test Cases (Binding minimum)

| ID | Area | Case | Expected |
|----|------|------|----------|
| T-01 | API | POST valid idea | 200 + 6 ordered sections |
| T-02 | API | Missing title | 422 |
| T-03 | API | Empty description | 422 |
| T-04 | API | No features | 200, default bullet present |
| T-05 | API | GET /api/health | 200 `{status: ok}` |
| T-06 | UI | Submit valid idea | spec renders, history entry added |
| T-07 | UI | Submit empty form | inline errors, no request sent |
| T-08 | UI | Backend down | error banner, previous state preserved |
| T-09 | UI | Reload page | history restored from localStorage |
| T-10 | UI | Copy + Download .md | clipboard contains headings; file downloads |

## 3. Exit Criteria

- All T-01…T-10 pass. No `tsc` errors. No `ruff` errors. Manual smoke signed in PR.
