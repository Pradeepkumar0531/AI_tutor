"""Centralized event creation + tenant-scoped reads (Prompt 11).

Existing services already append via ``EventRepository`` at their own sites;
this service is the contract for any new writes (validated type, verified
ownership, sanitized payloads) and the single read path for feeds/analytics.
No business logic moves here.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.enums import EventType
from app.models.ops import Event
from app.repositories.intelligence import EventRepository
from app.repositories.projects import ProjectRepository
from app.services.base import BaseService

log = logging.getLogger("app.services.events")

# Payload keys that must never reach the event log (case-insensitive
# substring match, applied recursively one level deep for nested dicts).
_SENSITIVE_FRAGMENTS = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "prompt",
    "answer",
    "content",
    "conversation",
)


def _sensitive(key: object) -> bool:
    lowered = str(key).lower()
    if lowered == "id" or lowered.endswith("_id"):
        return False  # ID references are safe pointers, not content
    return any(fragment in lowered for fragment in _SENSITIVE_FRAGMENTS)


def sanitize_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop sensitive keys from a payload copy. Defense in depth: existing
    call sites already emit safe payloads; the feed exposes this guarantee."""
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise BadRequestError("Event payload must be an object.")
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if _sensitive(key):
            continue
        if isinstance(value, dict):
            clean[str(key)] = {k: v for k, v in value.items() if not _sensitive(k)}
        else:
            clean[str(key)] = value
    return clean


class EventService(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.events = EventRepository(session)
        self.projects = ProjectRepository(session)

    def record(
        self,
        *,
        event_type: EventType | str,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        """Validated append (no commit — the caller's transaction owns it)."""
        if isinstance(event_type, str):
            try:
                event_type = EventType(event_type)
            except ValueError as e:
                raise BadRequestError(f"Unknown event type: {event_type}.") from e
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return self.events.append(
            event_type=event_type,
            user_id=user_id,
            project_id=project.id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=sanitize_payload(payload),
        )

    def feed(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        event_types: list[EventType] | list[str] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Event], int]:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        coerced: list[EventType] | None = None
        if event_types is not None:
            coerced = []
            for item in event_types:
                if isinstance(item, EventType):
                    coerced.append(item)
                    continue
                try:
                    coerced.append(EventType(str(item)))
                except ValueError as e:
                    raise BadRequestError(f"Unknown event type: {item}.") from e
        return self.events.feed(
            project.id,
            user_id,
            event_types=coerced,
            since=since,
            until=until,
            page=page,
            page_size=page_size,
        )
