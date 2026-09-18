# Learning Context

Persistent *relevant* learner state (PRD §11) — the differentiator between a
chatbot and a learning companion. One `learning_contexts` row per
(user, project); rewritten (never appended) on every refresh, so duplicate
processing converges instead of duplicating.

## What's stored (derived only)

- `learning_goal`: snapshot of the project goal.
- `strengths` / `weaknesses`: top concepts by mastery band (≥80 / <50).
- `repeated_mistakes`: concepts with ≥2 misses across the last 20 attempts
  (`{concept, misses, window}`) — counted from real `QuestionAttempt` history.
- `notes`: short derived facts (declining mastery, active patterns).

Never stored: raw conversation history, full prompts/answers, secrets.

## Flow

```
Assessment completed
  → MasteryService.update_from_assessment
  → LearningContextService.refresh_from_assessment   (rewrite, idempotent)
  → RecommendationService (consumes repeated patterns → targeted PRACTICE_QUIZ)
  → Tutor reads a ≤1200-char slice via context_for_tutor()
```

The tutor receives goal + weaknesses + repeated mistakes + strengths as one
bounded block inside the existing LEARNING CONTEXT prompt section — never full
history (PRD: relevance over volume). When nothing useful is known the block
is omitted entirely.

## Repeated-mistake workflow (PRD §13)

Repeated mistake (≥2 incorrect on one concept, last 20 attempts)
  → pattern recorded in `learning_contexts.repeated_mistakes`
  → `RecommendationService._repeated_mistake_candidates` emits a priority-90
     targeted practice rec naming the pattern
  → standard `find_active_scope` dedup keeps it idempotent; `_expire_resolved`
     retires it once mastery proves the gap closed.
