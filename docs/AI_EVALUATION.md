# AI Evaluation

Curated behavioral evaluation for the four PRD §14 areas (16 cases in
`app/evaluation/cases.py`, executed by `app/evaluation/runner.py`).

## What it is / isn't

- **Automated behavioral tests** (this framework): deterministic contracts —
  grounded answers cite, unsupported questions demur, grading matches
  answer keys, missed concepts resurface, weak/repeated-mistake/declining
  states recommend, mastered states stay quiet.
- **Unit/integration tests** (`tests/test_*.py`): component behavior incl.
  strategy weights, structured-output validation, idempotency.
- **Model-based evaluation**: none. No LLM-judge anywhere.
- **Human review**: none performed; no human quality scores are claimed.

## Execution model (honest by design)

- Deterministic test doubles only (`FakeChatProvider`,
  `DeterministicEmbeddingProvider`) — no cost, no network, reproducible.
- Sandbox: scratch user/space/project/material rows are created inside
  savepoints and **rolled back**. Only run summary + case results persist
  (`evaluation_runs` / `evaluation_results`: category, case, pass/fail,
  score, reason, expected, actual — no learner content, prompts, or secrets).
- Triggered from pytest (`tests/test_ai_evaluation.py`, asserts 16/16) or
  from the admin endpoint `POST /api/v1/admin/evaluations/run`
  (synchronous, bounded, same rollback guarantee).

## Cases

| Category | Cases |
|---|---|
| Tutor | grounded answer + citation; unsupported → insufficient-evidence; injection override treated as data (no secret/system leak); empty project never cites foreign material |
| Retrieval | on-topic query hits with material+page provenance; nonsense query → insufficient; empty project returns nothing foreign; provenance present on every hit |
| Assessment | generated questions validate; correct MCQ accepted / wrong rejected; reference answer scores ≥0.5 with explanatory feedback + understood concepts; missed concept resurfaces in next quiz |
| Recommendations | low mastery → active rec; 2-miss pattern → targeted rec naming it; declining → guidance; all-mastered → silence |

## Regression awareness

Prompts live in `app/ai/prompts.py`, selection in the assessment strategy,
rules in `RecommendationService` — any change there can flip cases. Run the
suite (`pytest tests/test_ai_evaluation.py` or the admin button) after touching
them; the admin view keeps per-category history with recent failures.

## Known limitations

- Fake providers prove *wiring and contracts*, not live-model quality.
  Groundedness with Groq/Gemini, real retrieval relevance at scale, and
  cost/latency under load remain manually verifiable only (see LIMITATIONS.md).
- No quality percentages are reported beyond case pass counts — anything else
  would be fabricated.
