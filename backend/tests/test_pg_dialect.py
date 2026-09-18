"""Postgres-dialect validation without a live database.

Compiles every table's CREATE TABLE against the PostgreSQL dialect (catches bad
Vector/UUID/Enum/JSONB usage) and asserts the hand-written migration covers the
full schema: extension, all tables, enum lifecycle.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import app.models  # noqa: F401
from app.db.base import Base

MIGRATION = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0001_initial_domain.py"
)


def test_all_tables_compile_for_postgres() -> None:
    # 24 domain tables + learning_contexts, ai_usage, evaluation_runs,
    # evaluation_results (migration 0010).
    assert len(Base.metadata.tables) == 28
    for name, table in Base.metadata.tables.items():
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert f"CREATE TABLE {name}" in ddl, name


def test_chunk_embedding_is_vector_768() -> None:
    ddl = str(
        CreateTable(Base.metadata.tables["document_chunks"]).compile(dialect=postgresql.dialect())
    )
    assert "VECTOR(768)" in ddl


def test_jsonb_used_for_flexible_columns() -> None:
    ddl = str(CreateTable(Base.metadata.tables["events"]).compile(dialect=postgresql.dialect()))
    assert "JSONB" in ddl


def test_migration_covers_full_schema() -> None:
    src = MIGRATION.read_text()
    assert 'CREATE EXTENSION IF NOT EXISTS "vector"' in src
    assert 'revision: str = "0001_initial_domain"' in src
    assert "down_revision: str | None = None" in src
    # Tables added by later migrations (question/assessment/mastery/image
    # tables) must appear in at least one version file — the chain as a whole
    # covers the schema, with a single head.
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    chain = "".join(p.read_text() for p in sorted(versions.glob("*.py")))
    for table in Base.metadata.tables:
        assert f'"{table}"' in chain, f"migration chain missing table {table}"
    assert "def upgrade() -> None:" in src
    assert "def downgrade() -> None:" in src
    for _, enum_name in [("MaterialType", "material_type"), ("EventType", "event_type")]:
        assert enum_name in src


def test_knowledge_event_migration_chain() -> None:
    """Migration 0004 extends event_type safely: single head, PG-guarded ALTERs,
    no-op downgrade (Neon execution stays pending — no DATABASE_URL here)."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    src = (versions / "0004_knowledge_events.py").read_text()
    assert 'revision: str = "0004_knowledge_events"' in src
    assert 'down_revision: str | None = "0003_space_created_event"' in src
    for value in (
        "EMBEDDING_STARTED",
        "EMBEDDING_COMPLETED",
        "EMBEDDING_FAILED",
        "CONCEPTS_EXTRACTED",
    ):
        assert value in src
    assert 'dialect.name != "postgresql"' in src  # SQLite runs skip ALTER TYPE
    # Model and migration agree on the full event vocabulary.
    from app.models.enums import EventType

    names = {e.value for e in EventType}
    assert {
        "EMBEDDING_STARTED",
        "EMBEDDING_COMPLETED",
        "EMBEDDING_FAILED",
        "CONCEPTS_EXTRACTED",
    } <= names
