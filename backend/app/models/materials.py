"""Learning material chain: Material (logical resource) -> Document (parsed
representation) -> DocumentChunk (RAG unit with pgvector embedding) +
DocumentImage (extracted embedded raster with page provenance).

Only storage references live here — PDF binaries and image renditions go to
Neon Object Storage (prod) or local storage (dev), never PostgreSQL. One
Material has at most one Document (unique); the relationship is shaped so
document versioning can evolve later.
Image binaries are content-addressed by SHA-256 (duplicates share one object);
every page occurrence keeps its own row so provenance is never lost.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ExtractionMethod, MaterialStatus, MaterialType
from app.models.mixins import EMBEDDING_DIMENSIONS, FlexibleJSON, TimestampMixin

if TYPE_CHECKING:
    from app.models.learning import Project


class Material(Base, TimestampMixin):
    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    type: Mapped[MaterialType] = mapped_column(
        sa.Enum(MaterialType, name="material_type"), nullable=False, default=MaterialType.PDF
    )
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[MaterialStatus] = mapped_column(
        sa.Enum(MaterialStatus, name="material_status"),
        nullable=False,
        default=MaterialStatus.QUEUED,
        index=True,
    )
    storage_provider: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="local")
    storage_key: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    checksum: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    processing_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.CheckConstraint("file_size IS NULL OR file_size >= 0", name="ck_materials_file_size"),
        sa.CheckConstraint("retry_count >= 0", name="ck_materials_retry_count"),
        # Anchor for DocumentImage composite FKs (same pattern as
        # QuestionConcept): image links resolve through their own project.
        sa.UniqueConstraint("project_id", "id", name="uq_materials_project_id"),
    )

    project: Mapped[Project] = relationship(back_populates="materials")
    document: Mapped[Document | None] = relationship(
        back_populates="material",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    material_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    extraction_method: Mapped[ExtractionMethod | None] = mapped_column(
        sa.Enum(ExtractionMethod, name="extraction_method"), nullable=True
    )
    language: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    doc_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", FlexibleJSON, nullable=True
    )

    __table_args__ = (
        sa.CheckConstraint("page_count IS NULL OR page_count >= 0", name="ck_documents_pages"),
        sa.UniqueConstraint("project_id", "id", name="uq_documents_project_id"),
    )

    material: Mapped[Material] = relationship(back_populates="document")
    project: Mapped[Project] = relationship(back_populates="documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    images: Mapped[list[DocumentImage]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="DocumentImage.document_id",
    )


class DocumentChunk(Base, TimestampMixin):
    """RAG retrieval unit. ``embedding`` is 768-d (Google gemini-embedding-001,
    truncated via output_dimensionality).

    Vector search strategy: exact (brute-force) scan scoped by ``project_id``.
    At assignment scale this is faster and simpler than an approximate index, which
    pgvector only recommends past ~10k+ vectors and which would require maintenance
    tuning. When chunks exceed ~100k rows, add an HNSW index with
    ``vector_cosine_ops`` in a new migration. See docs/DATABASE.md.
    """

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    page_start: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    token_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        # none_as_null keeps SQLite semantics identical to PostgreSQL (Python
        # None <-> SQL NULL), so IS NULL / IS NOT NULL filters behave the same
        # in tests as they do against pgvector in production.
        Vector(EMBEDDING_DIMENSIONS).with_variant(JSON(none_as_null=True), "sqlite"),
        nullable=True,
    )
    chunk_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", FlexibleJSON, nullable=True
    )

    __table_args__ = (
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_chunks_index"),
        sa.CheckConstraint("page_start IS NULL OR page_start >= 0", name="ck_chunks_page_start"),
        sa.CheckConstraint("token_count IS NULL OR token_count >= 0", name="ck_chunks_tokens"),
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
    project: Mapped[Project] = relationship(back_populates="chunks")


class DocumentImage(Base, TimestampMixin):
    """One embedded-raster occurrence on a document page. Binaries live in
    storage under a SHA-256 content key (duplicate binaries share one object);
    every page placement keeps its own row so provenance is exact.

    Project isolation is enforced at the database level: the composite FKs
    guarantee ``Material.project_id == Document.project_id ==
    DocumentImage.project_id`` (same pattern as ``QuestionConcept``). The
    older single-column FKs are retained; the composite ones are authoritative.
    """

    __tablename__ = "document_images"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    image_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    width: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    height: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=0)
    storage_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["documents.project_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_docimg_document_in_project",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "material_id"],
            ["materials.project_id", "materials.id"],
            ondelete="CASCADE",
            name="fk_docimg_material_in_project",
        ),
        sa.UniqueConstraint(
            "document_id", "page_number", "image_index", name="uq_docimg_document_page_index"
        ),
        sa.Index("ix_docimg_document_page", "document_id", "page_number"),
        sa.CheckConstraint("page_number >= 1", name="ck_docimg_page"),
        sa.CheckConstraint("image_index >= 0", name="ck_docimg_index"),
        sa.CheckConstraint("width >= 1", name="ck_docimg_width"),
        sa.CheckConstraint("height >= 1", name="ck_docimg_height"),
        sa.CheckConstraint("file_size >= 0", name="ck_docimg_file_size"),
    )

    document: Mapped[Document] = relationship(back_populates="images", foreign_keys=[document_id])
