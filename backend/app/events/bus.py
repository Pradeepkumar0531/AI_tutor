"""Domain event bus boundary (in-process for now; enables future analytics/events)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable

log = logging.getLogger("app.events")

_subscribers: dict[str, list[Callable]] = defaultdict(list)


def subscribe(event: str, handler: Callable) -> None:
    _subscribers[event].append(handler)


def publish(event: str, payload: dict | None = None) -> None:
    for handler in _subscribers.get(event, []):
        try:
            handler(payload or {})
        except Exception:  # noqa: BLE001
            log.exception("event handler failed event=%s", event)
