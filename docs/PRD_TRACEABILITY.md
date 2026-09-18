# PRD Traceability (PRD v3.0 → Implementation)

Status: `COMPLETE` = implemented + tested. `PARTIAL` = exists but gap remains.
`MISSING` = to build in Prompt 12.5. `EXTERNAL` = needs human infra step.

## Product / learning loop

| PRD Requirement | Status | Implementation | Tests/Evidence |
|---|---|---|---|
| Space → Project → Material → Knowledge → Tutor → Quiz → Assessment → Mastery → Growth → Analytics → Recommendation → Continue Learning | COMPLETE | `app/services/*`, routes under `/api/v1/projects`, `ProjectDetailPage` | backend suite, E2E journey, `scripts/smoke_test.py` |
| Spaces, Projects, project context, project-level isolation | COMPLETE | `learning.py`, ownership deps, composite FKs | isolation matrices, E2E tenant specs |
| PDF materials (text/tables/images/diagrams/scanned), async states, retry/recovery | COMPLETE | `documents/*`, `jobs/*`, `storage/*` | `test_materials/processing/document_images` |
| Grounded tutor, citations, insufficient-evidence, injection protection | COMPLETE | `tutor_service.py`, `rag/*`, prompts | `test_tutor.py`, tutor E2E |
| MCQ + open-ended quiz, adaptive selection (multi-signal), explanatory feedback | COMPLETE | `assessment_service.py`, `ai/quiz.py` | `test_assessment.py`, assessment E2E |
| Concept mastery (estimate), growth Improving/Stable/Attention, rule recommendations | COMPLETE | `mastery/growth/recommendation_service.py` | mastery/growth E2E |
| Events, project analytics, activity, downstream workflows, idempotency | COMPLETE | `Event`, `analytics_service.py`, jobs | analytics tests, dashboard E2E |
| Reliability/security/performance posture | COMPLETE | Prompt 12 hardening | `test_security.py` (26+) |

## Gaps closed in Prompt 12.5

| PRD Requirement | Status | Implementation | Tests/Evidence |
|---|---|---|---|
| Admin role + server-side RBAC | COMPLETE | `users.role`, migration `0010`, `require_admin`, `ADMIN_EMAILS` bootstrap | `test_admin.py` RBAC matrix |
| Admin Dashboard (users, spaces, projects, activity, engagement, analytics, AI usage, AI eval, jobs, health) | COMPLETE | `/api/v1/admin/*` (`AdminService`, aggregate SQL), `/admin` UI | backend + frontend + E2E admin spec |
| Global learner analytics (user-scoped) | COMPLETE | `GET /api/v1/analytics/summary`, `/analytics` UI | isolation tests |
| Home: Continue Learning, Recent, Progress, Attention, Next Action | COMPLETE | `GET /api/v1/home`, Home rework | backend + frontend + E2E |
| Persistent relevant learning context | COMPLETE | `learning_contexts`, `LearningContextService`, tutor injection (bounded) | `test_learning_context.py` |
| Repeated-mistake → pattern → context → targeted recommendation | COMPLETE | deterministic rule in context refresh + rec rule | idempotency + linkage tests |
| Persisted AI usage (model/feature/latency/tokens/cost/success) | COMPLETE | `ai_usage`, `AiUsageService`, 5 recording sites | `test_ai_usage.py` |
| AI evaluation framework (tutor/retrieval/assessment/recommendations) | COMPLETE | `app/evaluation/*`, sandbox runner, `evaluation_runs/results`, `docs/AI_EVALUATION.md` | `test_ai_evaluation.py` |
| Admin visibility: jobs, health, AI usage, evaluations, filtered activity | COMPLETE | admin endpoints (paginated, secret-free) | `test_admin.py` |
| `docs/PRD_TRACEABILITY.md`, `ADMIN.md`, `LEARNING_CONTEXT.md`, `AI_EVALUATION.md`, `DEVELOPMENT_PROMPTS.md` | COMPLETE | docs/ | review |

## External dependencies (not code gaps)

| Item | Status | Note |
|---|---|---|
| Public deployment URL, demo video | EXTERNAL | Requires human deploy step; `docs/DEPLOYMENT.md` is the runbook |
| Live Neon Object Storage verification | EXTERNAL | No bucket credentials; mocked-protocol tests only |
| Live Groq/Gemini verification | EXTERNAL | Keys exist locally but automated suite uses `TEST_FAKE_AI` by design |
