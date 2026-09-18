"""Tutor API contracts. No embeddings, storage keys, prompts, or provider payloads."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import MessageRole

MAX_MESSAGE_CHARS = 4000
MAX_REQUEST_KEY_CHARS = 64


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    request_key: str | None = Field(default=None, max_length=MAX_REQUEST_KEY_CHARS)

    @field_validator("content")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank.")
        return value


class CitationRead(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    material_id: uuid.UUID
    material_name: str
    page_start: int | None = None
    page_end: int | None = None
    label: str = ""


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    model: str | None = None
    created_at: datetime
    citations: list[CitationRead] = Field(default_factory=list)
    # App-computed response flags (persisted in tutor_metadata), so history
    # replay renders the same grounded/insufficient badges without sniffing
    # model prose. No prompts, embeddings, or provider payloads.
    grounded: bool = False
    insufficient_evidence: bool = False


class TutorSendResponse(BaseModel):
    conversation_id: uuid.UUID
    message: MessageRead
    citations: list[CitationRead] = Field(default_factory=list)
    grounded: bool = False
    insufficient_evidence: bool = False
