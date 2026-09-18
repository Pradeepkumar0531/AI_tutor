"""Shared Celery retry signaling. Tasks translate this into ``self.retry`` so the
core orchestration stays framework-free and unit-testable without a broker."""

from __future__ import annotations


class NeedsRetry(Exception):
    """Internal signal: execution requests a Celery retry with backoff."""

    def __init__(self, cause: Exception, countdown: int) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.countdown = countdown


def retry_countdown(attempt: int) -> int:
    return min(300, 15 * (2 ** max(0, attempt - 1)))
