"""Curated AI evaluation cases (registry). Outcomes persist to
``evaluation_runs``/``evaluation_results``; case definitions stay in code so
they are reviewable, versioned, and runnable both from pytest and from the
admin evaluation endpoint."""

from __future__ import annotations

CASES: list[dict] = [
    # Tutor
    {
        "case_id": "tutor.grounded_answer",
        "category": "tutor",
        "title": "Covered question returns grounded answer with citation",
    },
    {
        "case_id": "tutor.unsupported_question",
        "category": "tutor",
        "title": "Off-corpus question returns insufficient-evidence",
    },
    {
        "case_id": "tutor.injection_resists_override",
        "category": "tutor",
        "title": "Instruction override in content is treated as data",
    },
    {
        "case_id": "tutor.project_isolation",
        "category": "tutor",
        "title": "Empty project never cites another project's material",
    },
    # Retrieval
    {
        "case_id": "retrieval.relevant_chunks",
        "category": "retrieval",
        "title": "On-topic query retrieves project chunks with provenance",
    },
    {
        "case_id": "retrieval.irrelevant_query",
        "category": "retrieval",
        "title": "Nonsense query returns insufficient-evidence",
    },
    {
        "case_id": "retrieval.project_isolation",
        "category": "retrieval",
        "title": "Search never returns another project's chunks",
    },
    {
        "case_id": "retrieval.source_provenance",
        "category": "retrieval",
        "title": "Results carry material name + page range",
    },
    # Assessment
    {
        "case_id": "assessment.valid_generation",
        "category": "assessment",
        "title": "Generated questions validate (prompt/options/answer)",
    },
    {
        "case_id": "assessment.mcq_grading",
        "category": "assessment",
        "title": "Correct MCQ accepted, wrong MCQ rejected",
    },
    {
        "case_id": "assessment.open_ended_feedback",
        "category": "assessment",
        "title": "Open-ended evaluation scores + explains understood/missing",
    },
    {
        "case_id": "assessment.adaptive_resurface",
        "category": "assessment",
        "title": "Missed concept resurfaces in the next quiz",
    },
    # Recommendations
    {
        "case_id": "recommendations.weak_concept",
        "category": "recommendations",
        "title": "Low mastery produces an active practice/review recommendation",
    },
    {
        "case_id": "recommendations.repeated_mistakes",
        "category": "recommendations",
        "title": "Repeated-mistake pattern produces a targeted recommendation",
    },
    {
        "case_id": "recommendations.declining_trend",
        "category": "recommendations",
        "title": "Declining trend produces actional guidance",
    },
    {
        "case_id": "recommendations.caught_up",
        "category": "recommendations",
        "title": "Strong mastery everywhere yields no active recommendations",
    },
]

CATEGORIES = ("tutor", "retrieval", "assessment", "recommendations")
