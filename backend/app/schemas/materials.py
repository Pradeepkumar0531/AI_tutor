"""Material chain schemas (references only — binaries never touch the API)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ExtractionMethod, MaterialStatus, MaterialType
from app.schemas.knowledge import MaterialKnowledgeSummary


class MaterialCreate(BaseModel):
    project_id: uuid.UUID
    name: str
    original_filename: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class MaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    type: MaterialType
    status: MaterialStatus
    storage_provider: str
    original_filename: str | None
    mime_type: str | None
    file_size: int | None
    processing_error: str | None = None
    retry_count: int = 0
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    page_count: int | None = None
    chunk_count: int | None = None
    created_at: datetime
    updated_at: datetime


class DocumentDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_id: uuid.UUID
    project_id: uuid.UUID
    page_count: int | None
    extraction_method: ExtractionMethod | None
    language: str | None
    doc_metadata: dict[str, Any] | None = None
    chunk_count: int = 0
    image_count: int = 0
    created_at: datetime
    updated_at: datetime


class DocumentImageRead(BaseModel):
    """Learner-safe image metadata. The internal storage key, content hash,
    and raw bytes are never exposed here (bytes via the content endpoint)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    image_index: int
    width: int
    height: int
    mime_type: str
    file_size: int
    created_at: datetime


class MaterialDetailRead(BaseModel):
    """Material + processing state + document summary for status polling."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    type: MaterialType
    status: MaterialStatus
    storage_provider: str
    original_filename: str | None
    mime_type: str | None
    file_size: int | None
    processing_error: str | None = None
    retry_count: int = 0
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    document: DocumentDetailRead | None = None
    chunk_count: int = 0
    image_count: int = 0
    knowledge: MaterialKnowledgeSummary | None = None


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_id: uuid.UUID
    project_id: uuid.UUID
    page_count: int | None
    extraction_method: ExtractionMethod | None
    language: str | None


class ChunkRead(BaseModel):
    """Embeddings are excluded — retrieval responses cite chunk ids, not vectors."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID
    chunk_index: int
    content: str
    page_start: int | None
    page_end: int | None
    section_title: str | None
    chunk_metadata: dict[str, Any] | None


class ConceptCreate(BaseModel):
    project_id: uuid.UUID
    name: str
    description: str | None = None


class ConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
