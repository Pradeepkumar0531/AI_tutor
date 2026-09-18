"""Shared API schemas: pagination envelope + health payloads."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20


class HealthResponse(BaseModel):
    status: str
    service: str
