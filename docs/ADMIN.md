# Admin

Lightweight operational/product analytics interface (PRD §16, §20) — not
infrastructure monitoring. Every route is server-side gated by `require_admin`
(`app/auth/dependencies.py`); frontend hiding and the `/admin` route guard are
cosmetic. Learners get 403, anonymous callers 401 (matrix in
`tests/test_admin.py`).

## Roles

- `users.role`: `'learner'` (default) or `'admin'`. Plain string, no PG enum.
- Only privilege path: `ADMIN_EMAILS` (comma-separated) promotes on
  register/login. No public role-setting endpoint exists by design.
- Disabled accounts are rejected before the role check (403).

## API (`/api/v1/admin/*`)

| Endpoint | Purpose |
|---|---|
| `GET /overview` | COUNT aggregates: users/admins/spaces/projects/materials (+ready)/assessments/attempts/conversations/messages/active recs/events/AI calls/eval runs + jobs GROUP BY status |
| `GET /users` | Paginated user list (no hashes/tokens) |
| `GET /users/{id}` | Learning journey: spaces, projects, assessments, mastery snapshot, active recs, AI usage + cost, recent events |
| `GET /activity` | Platform events filtered by user/space/project/type/date range (space filter also matches space-level events via entity reference) |
| `GET /jobs` | Processing jobs with attempts, timestamps, 300-char safe error summaries; status filter |
| `GET /health` | API/database/worker-config/AI/storage/queue presence — booleans and names only, never secrets or connection strings |
| `GET /ai-usage/summary`, `GET /ai-usage` | Per (feature, provider, model) aggregates + recent rows |
| `GET /evaluations/summary`, `GET /evaluations` | Last run, per-category totals, recent failures |
| `POST /evaluations/run` | Executes the 16-case suite sandboxed (rolls back) and persists outcomes |

All lists are bounded (`limit` ≤ 100) and server-filtered; statuses are
`healthy`/`degraded` (a provider counts as configured only with care — see
`AdminService.health`, which never claims "live" from env vars alone).

## UI (`/admin`)

Tabs for Overview / Users (+inspect journey) / Activity / Jobs (status filter) /
AI usage / AI evaluation (run button + results) / Health. Loading, empty, and
error states throughout; no fake data.
