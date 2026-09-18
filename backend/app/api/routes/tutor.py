"""Tutor endpoints: conversations and grounded messages.

Every route verifies authenticated user -> owned project -> owned conversation.
Cross-tenant access returns 404 without disclosure. Business logic lives in
TutorService; routes only map HTTP to service calls.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_owned_project
from app.db.session import get_db
from app.models.learning import Project
from app.schemas.common import Page
from app.schemas.tutor import (
    CitationRead,
    ConversationCreate,
    ConversationRead,
    MessageCreate,
    MessageRead,
    TutorSendResponse,
)
from app.services.tutor_service import TutorService

router = APIRouter(prefix="/projects", tags=["tutor"])

SessionDep = Annotated[Session, Depends(get_db)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]


def _to_message_read(message) -> MessageRead:  # type: ignore[no-untyped-def]
    citations = [CitationRead(**c) for c in (message.citations or [])]
    metadata = message.tutor_metadata or {}
    return MessageRead(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        model=message.model,
        created_at=message.created_at,
        citations=citations,
        grounded=bool(metadata.get("grounded", False)),
        insufficient_evidence=bool(metadata.get("insufficient_evidence", False)),
    )


@router.post("/{project_id}/conversations", response_model=ConversationRead, status_code=201)
def create_conversation(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    body: ConversationCreate,
) -> ConversationRead:
    conversation = TutorService(session).create_conversation(
        user_id=user.id, project_id=project.id, title=body.title
    )
    return ConversationRead.model_validate(conversation)


@router.get("/{project_id}/conversations", response_model=list[ConversationRead])
def list_conversations(
    project: OwnedProject, user: CurrentUser, session: SessionDep
) -> list[ConversationRead]:
    conversations = TutorService(session).list_conversations(user_id=user.id, project_id=project.id)
    return [ConversationRead.model_validate(c) for c in conversations]


@router.get("/{project_id}/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> ConversationRead:
    conversation = TutorService(session).get_conversation(
        user_id=user.id, project_id=project.id, conversation_id=conversation_id
    )
    return ConversationRead.model_validate(conversation)


@router.get(
    "/{project_id}/conversations/{conversation_id}/messages",
    response_model=Page[MessageRead],
)
def list_messages(
    conversation_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> Page[MessageRead]:
    messages = TutorService(session).get_messages(
        user_id=user.id, project_id=project.id, conversation_id=conversation_id, limit=limit
    )
    items = [_to_message_read(m) for m in messages]
    return Page[MessageRead](items=items, total=len(items), page=1, page_size=limit)


@router.post(
    "/{project_id}/conversations/{conversation_id}/messages",
    response_model=TutorSendResponse,
)
async def send_message(
    conversation_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    body: MessageCreate,
) -> TutorSendResponse:
    exchange = await TutorService(session).send_message(
        user_id=user.id,
        project_id=project.id,
        conversation_id=conversation_id,
        content=body.content,
        request_key=body.request_key,
    )
    return TutorSendResponse(
        conversation_id=conversation_id,
        message=_to_message_read(exchange.assistant_message),
        citations=[CitationRead(**c) for c in exchange.citations],
        grounded=exchange.grounded,
        insufficient_evidence=exchange.insufficient_evidence,
    )
