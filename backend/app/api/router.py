"""Versioned API router registration. All routes live here, never in main.py."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.assessment import router as assessment_router
from app.api.routes.auth import router as auth_router
from app.api.routes.growth import router as growth_router
from app.api.routes.health import router as health_router
from app.api.routes.home import router as home_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.mastery import router as mastery_router
from app.api.routes.materials import router as project_materials_router
from app.api.routes.projects import router as projects_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.spaces import router as spaces_router
from app.api.routes.tutor import router as tutor_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(spaces_router)
api_router.include_router(projects_router)
api_router.include_router(project_materials_router)
api_router.include_router(knowledge_router)
api_router.include_router(tutor_router)
api_router.include_router(assessment_router)
api_router.include_router(analytics_router)
api_router.include_router(mastery_router)
api_router.include_router(growth_router)
api_router.include_router(recommendations_router)
api_router.include_router(admin_router)
api_router.include_router(home_router)
