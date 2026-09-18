"""Repository boundary: data access lives here, never raw SQL in services.

Transaction policy: repositories add/flush but never commit. The commit boundary is
the service layer (``services/base.py: transactional``) or, for simple request flows,
the ``get_db`` dependency. This lets one service operation span several repository
writes in a single atomic transaction.

Project isolation: every project-owned lookup takes ``project_id`` (or ``user_id``
for ownership roots) and returns ``None`` on scope mismatch instead of leaking a row.
"""

from __future__ import annotations

from typing import Generic, TypeVar

import sqlalchemy as sa
from sqlalchemy.orm import Session

T = TypeVar("T")
U = TypeVar("U")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class BaseRepository(Generic[T]):
    model: type[T]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, id_: object) -> T | None:
        return self.session.get(self.model, id_)

    def add(self, obj: U) -> U:
        """Persist any mapped object (joins included); never commits."""
        self.session.add(obj)
        return obj

    def flush(self) -> None:
        self.session.flush()

    def paginate(
        self, stmt: sa.Select, *, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE
    ) -> tuple[list[T], int]:
        """Bounded collection retrieval. Returns (items, total); clamps page_size."""
        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        total = self.session.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0
        items = list(self.session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
        return items, total
