"""User-scoped home + global analytics: Continue Learning across projects.

Both endpoints aggregate ONLY the caller's own projects (see
AnalyticsService.global_summary/home). Cold-start users get honest nulls and
empty lists — never fabricated progress.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.auth.dependencies import CurrentUser, SessionDep
from app.schemas.analytics import GlobalSummaryRead, HomeRead
from app.services.analytics_service import AnalyticsService

router = APIRouter(tags=["home", "analytics"])


@router.get("/analytics/summary", response_model=GlobalSummaryRead)
def global_summary(user: CurrentUser, session: SessionDep):
    summary = AnalyticsService(session).global_summary(user_id=user.id)
    return GlobalSummaryRead(**summary)


@router.get("/home", response_model=HomeRead)
def home(user: CurrentUser, session: SessionDep):
    return HomeRead(**AnalyticsService(session).home(user_id=user.id))
