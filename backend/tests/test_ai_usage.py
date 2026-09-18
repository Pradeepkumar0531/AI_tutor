"""AI usage ledger: recording, aggregates, cost honesty."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.ai_usage_service import AiUsageService, estimate_cost_usd
from tests.conftest import make_project, make_user


def test_estimate_cost_known_and_unknown() -> None:
    assert estimate_cost_usd("openai/gpt-oss-20b", 1_000_000, 1_000_000) == 0.60
    assert estimate_cost_usd("no-such-model", 100, 100) is None
    assert estimate_cost_usd("openai/gpt-oss-20b", None, None) is None


def test_record_and_summary(session: Session) -> None:
    user = make_user(session)
    project = make_project(session, user)
    svc = AiUsageService(session)
    svc.record(
        feature="tutor",
        provider="groq",
        model="openai/gpt-oss-20b",
        latency_ms=100,
        user_id=user.id,
        project_id=project.id,
        input_tokens=200,
        output_tokens=100,
    )
    svc.record(
        feature="tutor",
        provider="groq",
        model="openai/gpt-oss-20b",
        latency_ms=300,
        user_id=user.id,
        project_id=project.id,
        success=False,
        error_type="AITransientError",
    )
    session.commit()

    summary = svc.summary()
    assert len(summary) == 1
    row = summary[0]
    assert row["requests"] == 2 and row["failures"] == 1
    assert row["avg_latency_ms"] == 200.0
    assert row["input_tokens"] == 200 and row["output_tokens"] == 100
    assert row["estimated_cost_usd"] > 0
    assert svc.count() == 2
    assert svc.count(feature="quiz_generate") == 0
    recent = svc.recent(limit=10)
    assert len(recent) == 2
    assert {r.success for r in recent} == {True, False}
    failed = svc.recent(success=False)
    assert len(failed) == 1 and failed[0].error_type == "AITransientError"
    d = svc.to_dict(recent[0])
    assert d["feature"] == "tutor" and "created_at" in d
    assert "prompt" not in str(d).lower()


def test_summary_user_scoped(session: Session) -> None:
    user = make_user(session)
    other = make_user(session, email="other@example.com")
    svc = AiUsageService(session)
    svc.record(feature="tutor", provider="p", model="m", latency_ms=10, user_id=other.id)
    session.commit()
    assert svc.summary(user_id=user.id) == []
    assert len(svc.summary(user_id=other.id)) == 1
