"""Curated AI evaluation: 16 deterministic cases over real services.

Runs the sandbox runner (fake providers, rolled back afterwards) and asserts
every case passes — this is behavioral/contract evaluation, not human
judgment (see docs/AI_EVALUATION.md). The admin endpoint persists the same
results via ``persist_run`` (covered in test_admin.py).
"""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from app.evaluation.cases import CASES, CATEGORIES
from app.evaluation.runner import run_all


def test_registry_covers_all_categories() -> None:
    by_cat: dict[str, int] = {}
    for case in CASES:
        assert set(case) >= {"case_id", "category", "title"}
        by_cat[case["category"]] = by_cat.get(case["category"], 0) + 1
    for category in CATEGORIES:
        assert by_cat.get(category, 0) >= 3, f"thin category: {category}"


def test_all_cases_pass_with_fake_providers(session: Session) -> None:
    results = asyncio.run(run_all(session))
    session.rollback()  # sandbox rows never persist from tests
    assert len(results) == len(CASES)
    assert {r["case_id"] for r in results} == {c["case_id"] for c in CASES}
    failures = [r for r in results if not r["passed"]]
    assert not failures, failures
    for r in results:
        assert r["reason"], r["case_id"]
        assert set(r) >= {
            "case_id",
            "category",
            "passed",
            "score",
            "reason",
            "expected",
            "actual",
        }


def test_results_are_machine_readable(session: Session) -> None:
    from app.evaluation.runner import persist_run

    results = asyncio.run(run_all(session))
    session.rollback()
    run = persist_run(session, triggered_by_id=None, results=results)
    assert run.total_cases == len(CASES)
    assert run.passed == len(CASES) and run.failed == 0
    assert len(run.results) == len(CASES)
    by_cat = {c: 0 for c in CATEGORIES}
    for row in run.results:
        by_cat[row.category] += 1
        assert row.case_id and row.reason
    assert all(v > 0 for v in by_cat.values())
