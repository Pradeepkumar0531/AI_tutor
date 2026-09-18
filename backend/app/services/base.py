"""Service-layer base: transaction boundary + shared service plumbing.

Pattern for every domain operation::

    Route -> Service -> Repository -> Database

Services own the transaction: methods wrapped with ``@transactional`` commit on
success and roll back on failure, so multi-write operations (assessment completion,
mastery update + history + event) stay atomic. Repositories never commit.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from sqlalchemy.orm import Session

log = logging.getLogger("app.services")

P = ParamSpec("P")
R = TypeVar("R")


class BaseService:
    def __init__(self, session: Session) -> None:
        self.session = session


def transactional(fn: Callable[P, R]) -> Callable[P, R]:
    """Commit the session when the service method succeeds, roll back on error."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        service = args[0]
        session: Session = service.session  # type: ignore[attr-defined]
        try:
            result = fn(*args, **kwargs)
            session.commit()
            return result
        except Exception:
            session.rollback()
            log.exception("service transaction rolled back in %s", fn.__qualname__)
            raise

    return wrapper
