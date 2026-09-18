"""Persisted AI usage: queryable history behind Admin AI-usage views.

Complements ephemeral log lines (``app.ai.observability``): services call
``record()`` next to every ``log_ai_call`` with the same metadata plus the
request's user/project scope. Never stores prompts, answers, keys, or
document content. Cost is a rough static estimate for known models, else None.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

import sqlalchemy as sa

from app.models.observability import AiUsage
from app.services.base import BaseService

log = logging.getLogger("app.ai_usage")

# Rough blended USD per 1M tokens (input, output), documented estimates only.
# Unknown models record NULL cost rather than a fabricated number.
_MODEL_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-20b": (0.10, 0.50),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "models/gemini-embedding-001": (0.0, 0.0),
}


def estimate_cost_usd(
    model: str, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    prices = _MODEL_PRICES_PER_MTOK.get(model)
    if prices is None or (input_tokens is None and output_tokens is None):
        return None
    return round(
        (input_tokens or 0) / 1_000_000 * prices[0] + (output_tokens or 0) / 1_000_000 * prices[1],
        6,
    )


class AiUsageService(BaseService):
    """Append-only AI usage ledger + admin aggregates (SQL, never full scans)."""

    def record(
        self,
        *,
        feature: str,
        provider: str,
        model: str,
        latency_ms: int,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        success: bool = True,
        error_type: str | None = None,
        request_id: str | None = None,
    ) -> AiUsage:
        row = AiUsage(
            user_id=user_id,
            project_id=project_id,
            feature=feature,
            provider=provider,
            model=model,
            latency_ms=max(latency_ms, 0),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
            success=success,
            error_type=error_type,
            request_id=request_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def summary(
        self,
        *,
        since: datetime | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Per (feature, provider, model) aggregates: count, failures, avg
        latency, summed tokens/cost. Bounded GROUP BY — no row loading."""
        q = (
            sa.select(
                AiUsage.feature,
                AiUsage.provider,
                AiUsage.model,
                sa.func.count().label("requests"),
                sa.func.sum(sa.case((AiUsage.success.is_(False), 1), else_=0)).label("failures"),
                sa.func.avg(AiUsage.latency_ms).label("avg_latency_ms"),
                sa.func.sum(AiUsage.input_tokens).label("input_tokens"),
                sa.func.sum(AiUsage.output_tokens).label("output_tokens"),
                sa.func.sum(AiUsage.estimated_cost_usd).label("estimated_cost_usd"),
            )
            .group_by(AiUsage.feature, AiUsage.provider, AiUsage.model)
            .order_by(sa.func.count().desc())
            .limit(min(max(limit, 1), 200))
        )
        if since is not None:
            q = q.where(AiUsage.created_at >= since)
        if user_id is not None:
            q = q.where(AiUsage.user_id == user_id)
        rows = self.session.execute(q).all()
        return [
            {
                "feature": r[0],
                "provider": r[1],
                "model": r[2],
                "requests": r[3],
                "failures": r[4],
                "avg_latency_ms": round(float(r[5] or 0), 1),
                "input_tokens": r[6] or 0,
                "output_tokens": r[7] or 0,
                "estimated_cost_usd": round(float(r[8] or 0), 6),
            }
            for r in rows
        ]

    def count(
        self,
        *,
        user_id: uuid.UUID | None = None,
        feature: str | None = None,
    ) -> int:
        q = sa.select(sa.func.count()).select_from(AiUsage)
        if user_id is not None:
            q = q.where(AiUsage.user_id == user_id)
        if feature is not None:
            q = q.where(AiUsage.feature == feature)
        return self.session.scalar(q) or 0

    def recent(
        self,
        *,
        limit: int = 50,
        user_id: uuid.UUID | None = None,
        feature: str | None = None,
        success: bool | None = None,
    ) -> list[AiUsage]:
        q = sa.select(AiUsage).order_by(AiUsage.created_at.desc()).limit(min(max(limit, 1), 200))
        if user_id is not None:
            q = q.where(AiUsage.user_id == user_id)
        if feature is not None:
            q = q.where(AiUsage.feature == feature)
        if success is not None:
            q = q.where(AiUsage.success.is_(success))
        return list(self.session.scalars(q).all())

    @staticmethod
    def to_dict(row: AiUsage) -> dict:
        return {
            "id": str(row.id),
            "user_id": str(row.user_id) if row.user_id else None,
            "project_id": str(row.project_id) if row.project_id else None,
            "feature": row.feature,
            "provider": row.provider,
            "model": row.model,
            "latency_ms": row.latency_ms,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "estimated_cost_usd": row.estimated_cost_usd,
            "success": row.success,
            "error_type": row.error_type,
            "request_id": row.request_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
