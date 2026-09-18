"""Knowledge-layer API schemas. Embeddings and storage keys never appear here."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeTotals(BaseModel):
    chunks_total: int = 0
    chunks_embedded: int = 0
    concepts: int = 0
    materials_ready: int = 0


class KnowledgeStatusRead(BaseModel):
    project_id: uuid.UUID
    status: Literal["PENDING", "PROCESSING", "READY", "FAILED"]
    totals: KnowledgeTotals = Field(default_factory=KnowledgeTotals)


class ConceptMaterialLink(BaseModel):
    id: uuid.UUID
    name: str


class ConceptDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    materials: list[ConceptMaterialLink] = Field(default_factory=list)
    chunk_count: int = 0
    pages: list[int] = Field(default_factory=list)


class MaterialKnowledgeSummary(BaseModel):
    """Per-material knowledge state for the material detail view. A material
    must not look 'AI ready' before its embeddings actually exist."""

    status: Literal["PENDING", "PROCESSING", "READY", "FAILED"]
    embedded: int = 0
    total: int = 0
    image_count: int = 0
    images_by_page: dict[int, int] = Field(default_factory=dict)


class RetrievedChunkRead(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    material_id: uuid.UUID
    material_name: str
    text: str
    page_start: int | None
    page_end: int | None
    similarity: float


class CitationRead(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    material_id: uuid.UUID
    material_name: str
    page_start: int | None
    page_end: int | None
    label: str = ""


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int | None = Field(default=None, ge=1, le=50)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    material_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)


class SearchResponse(BaseModel):
    query: str
    results: list[RetrievedChunkRead] = Field(default_factory=list)
    citations: list[CitationRead] = Field(default_factory=list)
    context: str = ""
    insufficient_evidence: bool = False


class ReprocessKnowledgeResponse(BaseModel):
    material_id: uuid.UUID
    job_status: str
    reset: int = 0
