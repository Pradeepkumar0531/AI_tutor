# Mastery (Prompt 9 — implemented)

Per-concept, per-project, per-user understanding estimates derived
deterministically from immutable assessment evidence. No LLM, no black box:
every number traces to stored rows via a documented formula.

## Definition and scope

Mastery answers *how strong is the current estimate of understanding?* for one
`(user, project, concept)` triple; confidence answers *how much evidence
supports it?* Same concept names in different projects are independent rows
(`uq_mastery_user_project_concept`); there is no global learner mastery.

It is neither the latest quiz score nor correct/total: history always tempers
new evidence (update weight ≤ 0.5), so 90%→40% lands near 0.54, not 0.40, and
40%→90% improves without instant perfection.

## Storage (existing tables, one migration)

- `Mastery`: `score` 0-100 (existing scale/checks), `confidence` 0-1,
  `trend` (`IMPROVING/STABLE/DECLINING`), `last_assessed_at` (= source
  assessment's `completed_at`, deterministic), `updated_at`. API presents
  scores 0-1 (`/100`, one mapping point).
- `MasteryHistory` (append-only): `score`, `confidence`, `source`
  (`ASSESSMENT` for this engine), `assessment_id` (SET NULL survives
  assessment deletion), **`previous_score`** (migration `0007`) so every
  transition reads as previous → new.
- Migration `0007_mastery_engine` also adds
  `uq_mastery_history_mastery_assessment`: reprocessing one assessment for one
  concept cannot duplicate history (NULL assessment ids stay distinct).
  Single head; SQLite upgrade/downgrade executed in validation; PG uses
  standard DDL.

## Algorithm (`MasteryService`, `app/services/mastery_service.py`)

Per assessed concept, with observation `o` = clamped `normalized_score`
(partials contribute partially) and `q` = questions seen:

```
age_days = max(0, (assessment.completed_at - last_assessed_at).days)  # 0 if none
decay    = exp(-MASTERY_RECENCY_LAMBDA * age_days)      # default 0.02
old_d    = BASELINE + (old - BASELINE) * decay
conf_d   = conf_old * decay
alpha    = min(MAX_WEIGHT, BASE + PER_Q*(q-1) + HIST_BONUS*min(prior_obs, 10))
new      = (1 - alpha) * old_d + alpha * o
conf     = 1 - (1 - conf_d) * (1 - min(1, q/4) * 0.5)
```

Constants: `BASE=0.25`, `PER_Q=0.05`, `HIST_BONUS=0.02`, cap 10,
`MAX_WEIGHT=0.5` (`MASTERY_MAX_EVIDENCE_WEIGHT`), saturation 4 / update-max
0.5. Cold start: `(MASTERY_BASELINE=0.5, MASTERY_INITIAL_CONFIDENCE=0.2)` —
never 0 or 1, never "no evidence = zero knowledge". All values clamped 0-1.

Worked example (first correct answer, 1 question): old .5 → `.75*.5+.25*1 =
.625`; confidence `.2 → 1-.8*(1-.25*.5) = .3`.

## Evidence weighting, recency, confidence

- More questions per assessment → stronger update, saturating
  (`min(1, q/4)`); more history → slightly stronger updates, capped
  (`HIST_BONUS × min(prior, 10)`, `alpha ≤ 0.5`) — never exceeding 1.
- Recency has two honest mechanisms: EWMA order-weighting (recent
  observations dominate geometrically) and wall-clock decay of the prior
  toward baseline (`exp(-lambda·days)`, timestamps from immutable records —
  fully deterministic, no clock injection). No time-series framework.
- Confidence ≠ mastery: it tracks evidence volume/consistency only, rising
  with diminishing returns (one correct ≈ 0.3, many consistent → ~0.9+,
  asymptotically < 1).

## Cold start and trend

- No row → API returns baseline + initial confidence + `has_evidence: false`
  + empty recent; the UI says "Not yet established", never "0%".
- Trend (`IMPROVING/STABLE/DECLINING`, stored on the row): windowed mean
  comparison over the last `MASTERY_TREND_WINDOW` (5) post-update scores;
  fewer than 3 observations → `STABLE`; threshold `MASTERY_TREND_THRESHOLD`
  (0.05). Trend is a trajectory signal, not Growth (Prompt 10).

## Idempotency, concurrency, atomicity

- `update_from_assessment` is transactional per call: read (row-locked on
  PostgreSQL via `SELECT … FOR UPDATE`) → compute → write row + history +
  `MASTERY_UPDATED` event → commit. Applied pairs are skipped via the unique
  guard; `IntegrityError` triggers one rollback-and-retry converging to
  exactly-once. Only concepts in the assessment's `concept_results` update.
- Failure of one concept rolls back the whole application (all-or-nothing);
  assessment rows are only ever read, never mutated.

## Assessment integration

`AssessmentService.complete_attempt` finalizes + commits the immutable
assessment, then applies mastery in a **separate** transaction wrapped in
try/except: mastery faults are logged with the assessment id and never fail
completion. Synchronous by decision (fast, deterministic); assessment
completion is preserved by construction. A service-level `rebuild_concept`
replays history deterministically (no route; tests prove replay = live path).

## Quiz integration

`AssessmentService._build_context` now fills Prompt 8's `mastery_estimates`
from persisted rows (read-only, fault-tolerant → history-only fallback).
Verified: low-mastery concepts gain selection weight while coverage,
incorrect-history, difficulty, and diversity signals keep working.

## Tutor integration

`LearningContext.mastery_estimates` carries persisted mastery for the
question-relevant concepts only (bounded by the concept cap); the prompt
gains a capped "Learner mastery estimates" guidance section (depth
calibration, never grades). Lookup failures degrade silently to no-mastery.

## Explanation DTO

`MasteryExplanation` (service-level; `MasteryDetailRead` over HTTP):
score, confidence, trend, assessment/question evidence counts, recent C/P/I
(from the latest assessment's stored `recent`), up to 5 contributing
assessment ids, `has_evidence`. Built from stored data only — no LLM.

## API

- `GET /projects/{id}/mastery?page=&page_size=&sort=lowest|recent|name` —
  paginated estimates with concept names + observation counts.
- `GET /projects/{id}/mastery/{conceptId}` — full explanation; cold-start
  concepts return baseline with `has_evidence: false` (200, not 404).
- `GET /projects/{id}/mastery/{conceptId}/history?page=&page_size=` —
  newest-first transitions with previous/new scores + assessment ids.
- No write endpoints (POST/PUT/DELETE → 405); history immutable (no routes).
- All scoped `user → project → concept`, cross-tenant 404.

## Downstream: Growth + Recommendations (Prompt 10)

Mastery is consumed, never recomputed: `GrowthService` aggregates rows into
project status/counts/history; `RecommendationService` turns low/declining
mastery + recent mistakes + materials into deduplicated, lifecycle-managed
recommendations. Completion chain: assessment → mastery → growth →
recommendations (each step best-effort; the assessment stands regardless).
Growth reads derive per-concept status with the same rule the rows use, so
the aggregate never disagrees with the trail. No new mastery algorithm, no
LLM, no Growth classification beyond the existing trend vocabulary.

## Events and observability

`MASTERY_UPDATED` per concept with `{concept_id, assessment_id,
previous_score, new_score, confidence}` (0-1 scale, documented) — no answers,
prompts, keys, or AI outputs. "Why did mastery change?" is answerable from
history rows + the source assessment alone.

## Limitations (for Prompt 10)

- No wall-clock forgetting of stored rows (decay applies at update time).
- Evidence counts aggregate over full history (indexed PK lookups; fine at
  prototype scale, revisit with pagination cursors beyond it).
- Live Neon/Groq/Redis verification not performed (no credentials);
  validation is full-stack under `TEST_FAKE_AI` with the real algorithm.
