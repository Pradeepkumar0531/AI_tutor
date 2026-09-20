"""Grounded AI Tutor: project-scoped conversations over RAG evidence.

Flow per user message (business logic stays server-side)::

    authorize user -> project -> conversation
    tx1: persist user message (+ idempotency key, events)
    classify intent (deterministic rules, no model call)
    retrieve evidence via RetrievalService (grounded kinds only)
    build learning context + trust-bounded prompt
    call Groq (bounded retry on transient failures only)
    tx2: persist assistant message + app-built citations + events

The database transaction is NEVER held open across the Groq call: the user
message commits first, so a provider failure leaves consistent history and a
retry with the same request key resumes generation instead of duplicating.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.ai.errors import AITransientError, TutorGenerationFailed
from app.ai.observability import log_ai_call
from app.ai.prompts import build_tutor_prompt
from app.ai.schemas import TutorStructuredOutput
from app.core.config import Settings, get_settings
from app.core.exceptions import BadRequestError, NotFoundError, ServiceUnavailableError
from app.models.enums import EventType, MessageRole
from app.models.knowledge import Concept
from app.models.learning import Project
from app.models.tutor import Conversation, Message
from app.models.users import User
from app.repositories.intelligence import EventRepository
from app.repositories.knowledge import ConceptRepository, ConversationRepository, MessageRepository
from app.repositories.projects import ProjectRepository
from app.services.base import BaseService, transactional

log = logging.getLogger("app.services.tutor")

MAX_MESSAGE_CHARS = 4000


class QuestionKind(enum.StrEnum):
    PROJECT_GROUNDED = "PROJECT_GROUNDED"
    GENERAL_LEARNING = "GENERAL_LEARNING"
    CLARIFICATION = "CLARIFICATION"
    UNSUPPORTED = "UNSUPPORTED"


_UNIVERSAL_ACTION_PATTERNS = [
    re.compile(
        r"\b(delete|remove|drop|erase)\b.*\b(project|space|material|account|user|data|conversation)\b"
    ),
    re.compile(
        r"\b(show|reveal|give|tell|display|print)\b.*\b(password|secret|api[_\s-]?key|token)\b"
    ),
    re.compile(r"\b(system prompt|prompt injection|jailbreak)\b"),
    re.compile(
        r"\b(call|invoke|run|execute)\b.*\b(api|tool|function|code|sql|query|command|admin)\b"
    ),
    re.compile(r"\badmin\b"),
]

_CLARIFICATION_PATTERNS = [
    re.compile(
        r"^(can you|could you|please )?(explain that|explain this|explain it"
        r"|what do you mean|tell me more|go on|elaborate)\.?$"
    ),
    re.compile(r"^(why|how come)\??$"),
    re.compile(r"^(huh|what)\??$"),
]

_MATERIAL_REFERENCE_PATTERNS = [
    re.compile(
        r"\b(pdf|document|material|reading|chapter|notes|paper|textbook|slides|lecture|pages?)\b"
    ),
    re.compile(r"\baccording to\b"),
    re.compile(r"\bupload(ed|s)?\b"),
    re.compile(r"\bmy (file|files|materials|documents|notes|readings)\b"),
    re.compile(r"\bthis (topic|material|document|chapter|paper|reading)\b"),
    re.compile(r"\bthese materials\b"),
]

_REFERENTIAL_TOKENS = re.compile(r"\b(that|this|it|they|those|these|you mean|more)\b")


def classify_intent(content: str, *, has_history: bool) -> QuestionKind:
    """Deterministic intent routing. No model call, no side effects."""
    text = content.strip().lower()
    for pattern in _UNIVERSAL_ACTION_PATTERNS:
        if pattern.search(text):
            return QuestionKind.UNSUPPORTED
    if has_history:
        for pattern in _CLARIFICATION_PATTERNS:
            if pattern.search(text):
                return QuestionKind.CLARIFICATION
        if len(text) < 40 and _REFERENTIAL_TOKENS.search(text):
            return QuestionKind.CLARIFICATION
    for pattern in _MATERIAL_REFERENCE_PATTERNS:
        if pattern.search(text):
            return QuestionKind.PROJECT_GROUNDED
    return QuestionKind.GENERAL_LEARNING


def format_chunks_for_tutor(chunks: list) -> str:
    """Backward-compatible alias — chunk rendering lives in
    ``app.rag.retrieval.format_chunks_for_prompt`` (shared with quizzes)."""
    from app.rag.retrieval import format_chunks_for_prompt

    return format_chunks_for_prompt(chunks)


def _strip_rag_delimiters(text: str, *, begin: str, end: str) -> str:
    """Return the inner blocks of a ``build_rag_context`` payload without its
    outer trust-boundary wrapper. Falls back to the raw text when delimiters
    are absent (never drops evidence)."""
    inner = text.strip()
    if begin in inner:
        inner = inner.split(begin, 1)[1]
    if end in inner:
        inner = inner.rsplit(end, 1)[0]
    return inner.strip()


@dataclass
class LearningContext:
    project_name: str
    learning_goal: str | None = None
    target_outcome: str | None = None
    difficulty: str | None = None
    history: list[tuple[str, str]] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    mastery_estimates: dict[str, float] = field(default_factory=dict)
    evidence_text: str = ""
    has_evidence: bool = False
    citation_dicts: list[dict] = field(default_factory=list)
    insufficient: bool = False
    top_similarity: float | None = None
    retrieval_latency_ms: int = 0
    # Bounded persistent-learner slice (goal/weaknesses/repeated mistakes);
    # empty when nothing useful is known. Never full history.
    persistent_context: str = ""


@dataclass
class TutorExchange:
    user_message: Message
    assistant_message: Message
    citations: list[dict]
    grounded: bool
    insufficient_evidence: bool
    is_retry_replay: bool = False


INSUFFICIENT_ANSWER = (
    "I couldn't find enough evidence in this project's materials to answer that "
    "confidently. Try uploading material that covers the topic, or rephrase with "
    "terms from your readings."
)

UNSUPPORTED_ANSWER = (
    "I can't help with that — I'm a learning tutor without tools or admin access, "
    "so I can't change anything, reveal secrets, or call external systems. "
    "Ask me about your project materials or a learning topic instead."
)


class TutorService(BaseService):
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        ai_service=None,  # AIService; untyped to avoid import weight here
    ) -> None:
        super().__init__(session)
        self.settings = settings or get_settings()
        self.ai_service = ai_service
        self.projects = ProjectRepository(session)
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.concepts = ConceptRepository(session)
        self.events = EventRepository(session)

    def _ai(self):
        if self.ai_service is None:
            from app.ai.service import ai_service

            return ai_service
        return self.ai_service

    # ---------------------------------------------------------- conversations

    @transactional
    def create_conversation(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, title: str | None = None
    ) -> Conversation:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        conversation = self.conversations.create(
            project_id=project.id,
            user_id=user_id,
            title=(title.strip() if title and title.strip() else "New conversation"),
        )
        self.session.flush()
        self.events.append(
            event_type=EventType.CONVERSATION_CREATED,
            user_id=user_id,
            project_id=project.id,
            entity_type="conversation",
            entity_id=conversation.id,
        )
        return conversation

    def list_conversations(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[Conversation]:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return self.conversations.list_for_project(project.id, user_id)

    def get_conversation(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        conversation = self.conversations.get_for_project(conversation_id, project.id, user_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        return conversation

    def get_messages(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        conversation_id: uuid.UUID,
        limit: int = 100,
    ) -> list[Message]:
        conversation = self.get_conversation(
            user_id=user_id, project_id=project_id, conversation_id=conversation_id
        )
        return self.messages.history(conversation.id, limit=min(max(limit, 1), 200))

    # ---------------------------------------------------------- send flow

    async def send_message(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        conversation_id: uuid.UUID,
        content: str,
        request_key: str | None = None,
    ) -> TutorExchange:
        """Two-transaction flow: persist user message first, generate after."""
        cleaned = (content or "").strip()
        if not cleaned:
            raise BadRequestError("Message must not be blank.")
        if len(cleaned) > MAX_MESSAGE_CHARS:
            raise BadRequestError(f"Message exceeds the {MAX_MESSAGE_CHARS} character limit.")
        key = request_key.strip() if request_key and request_key.strip() else None
        if self.session.get(User, user_id) is None:
            raise NotFoundError("User not found.")
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        conversation = self.conversations.get_for_project(conversation_id, project.id, user_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")

        user_message, replay = self._persist_user_message(
            user_id=user_id,
            project=project,
            conversation=conversation,
            content=cleaned,
            request_key=key,
        )
        if replay is not None:
            return replay
        return await self._generate_exchange(
            user_id=user_id,
            project=project,
            conversation=conversation,
            user_message=user_message,
        )

    @transactional
    def _persist_user_message(
        self,
        *,
        user_id: uuid.UUID,
        project: Project,
        conversation: Conversation,
        content: str,
        request_key: str | None,
    ) -> tuple[Message, TutorExchange | None]:
        """Transaction 1. Returns (user_message, replay_or_None). A retried
        request key resolves to the persisted exchange: the existing assistant
        reply when present, otherwise a regeneration pass over the SAME user
        message (never a duplicate)."""
        if request_key:
            existing = self.messages.find_by_request_key(conversation.id, request_key)
            if existing is not None:
                return existing, self._rebuild_exchange(
                    project=project,
                    conversation=conversation,
                    user_message=existing,
                )
        message = self.messages.append(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=content,
            request_key=request_key,
        )
        self.session.flush()
        if conversation.title == "New conversation":
            conversation.title = (content[:60] + "…") if len(content) > 60 else content
        self.events.append(
            event_type=EventType.TUTOR_MESSAGE,
            user_id=user_id,
            project_id=project.id,
            entity_type="message",
            entity_id=message.id,
        )
        return message, None

    def _rebuild_exchange(
        self, *, project: Project, conversation: Conversation, user_message: Message
    ) -> TutorExchange | None:
        """Find the assistant reply that followed an idempotent user message."""
        reply = self.session.scalar(
            sa.select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.role == MessageRole.ASSISTANT,
                Message.created_at > user_message.created_at,
            )
            .order_by(Message.created_at, Message.id)
            .limit(1)
        )
        if reply is None:
            return None
        citations = [dict(c) for c in (reply.citations or [])]
        metadata = reply.tutor_metadata or {}
        return TutorExchange(
            user_message=user_message,
            assistant_message=reply,
            citations=citations,
            grounded=bool(metadata.get("grounded", bool(citations))),
            insufficient_evidence=bool(metadata.get("insufficient_evidence", False)),
            is_retry_replay=True,
        )

    async def _generate_exchange(
        self,
        *,
        user_id: uuid.UUID,
        project: Project,
        conversation: Conversation,
        user_message: Message,
    ) -> TutorExchange:
        settings = self.settings
        history = self._bounded_history(conversation.id, settings)
        kind = classify_intent(user_message.content, has_history=bool(history))

        if kind == QuestionKind.UNSUPPORTED:
            return self._persist_assistant(
                user_id=user_id,
                project=project,
                conversation=conversation,
                user_message=user_message,
                answer=UNSUPPORTED_ANSWER,
                citations=[],
                grounded=False,
                insufficient_evidence=False,
                kind=kind,
                model=None,
                provider=None,
                latency_ms=0,
                retrieval_count=0,
            )

        context = await self._assemble_context(
            user_id=user_id,
            project=project,
            kind=kind,
            question=user_message.content,
            history=history,
        )
        if kind == QuestionKind.PROJECT_GROUNDED and context.insufficient:
            return self._persist_assistant(
                user_id=user_id,
                project=project,
                conversation=conversation,
                user_message=user_message,
                answer=INSUFFICIENT_ANSWER,
                citations=[],
                grounded=False,
                insufficient_evidence=True,
                kind=kind,
                model=None,
                provider=None,
                latency_ms=0,
                retrieval_count=0,
            )

        output = await self._call_model(
            project=project,
            conversation=conversation,
            context=context,
            question=user_message.content,
        )
        if kind == QuestionKind.PROJECT_GROUNDED:
            # App-authoritative: retrieved evidence means grounded citations
            # even when the model is humble (see
            # test_app_overrides_model_grounded_claim).
            grounded = not context.insufficient and bool(context.citation_dicts)
            citations = context.citation_dicts
        elif kind == QuestionKind.GENERAL_LEARNING:
            # Opportunistic grounding: the model judges whether the retrieved
            # evidence actually answers the question. Weak retrieval routinely
            # clears the similarity threshold on short slide chunks, so
            # app-authoritative citations here would attach noise to general
            # answers — cite only evidence the model reports using.
            grounded = (
                bool(output.grounded) and not context.insufficient and bool(context.citation_dicts)
            )
            citations = context.citation_dicts if grounded else []
        else:
            grounded = False
            citations = []
        return self._persist_assistant(
            user_id=user_id,
            project=project,
            conversation=conversation,
            user_message=user_message,
            answer=output.answer,
            citations=citations,
            grounded=grounded,
            insufficient_evidence=False,
            kind=kind,
            model=output.model_name,
            provider=output.provider,
            input_tokens=output.input_tokens,
            output_tokens=output.output_tokens,
            latency_ms=output.latency_ms,
            retrieval_count=len(citations),
            needs_clarification=output.needs_clarification,
        )

    # ---------------------------------------------------------- context

    def _bounded_history(
        self, conversation_id: uuid.UUID, settings: Settings
    ) -> list[tuple[str, str]]:
        max_messages = min(max(settings.tutor_max_history_messages, 1), 100)
        max_chars = min(max(settings.tutor_max_history_chars, 256), 100_000)
        recent = self.messages.history(conversation_id, limit=max_messages)
        # history() returns newest-last; walk backwards to respect the budget,
        # then restore chronological order.
        kept: list[tuple[str, str]] = []
        total = 0
        for message in reversed(recent):
            role = "user" if message.role == MessageRole.USER else "assistant"
            size = len(message.content)
            if kept and total + size > max_chars:
                break
            kept.append((role, message.content))
            total += size
        kept.reverse()
        return kept

    async def _assemble_context(
        self,
        *,
        user_id: uuid.UUID,
        project: Project,
        kind: QuestionKind,
        question: str,
        history: list[tuple[str, str]],
    ) -> LearningContext:
        """Project metadata + bounded history + top overlapping concepts +
        RAG evidence (grounded kinds only). Missing values are omitted, never
        fabricated. The returned namespace also seeds Prompt 9+ fields
        (mastery, assessments, mistakes, growth) without touching this flow."""
        from app.rag.retrieval import RetrievalService

        settings = self.settings
        concepts: list[str] = []
        if kind in (QuestionKind.PROJECT_GROUNDED, QuestionKind.GENERAL_LEARNING):
            concepts = self._relevant_concepts(
                project_id=project.id,
                question=question,
                limit=min(max(settings.tutor_max_concepts, 1), 50),
            )

        evidence_text = ""
        citation_dicts: list[dict] = []
        insufficient = False
        top_similarity: float | None = None
        retrieval_latency_ms = 0
        # Retrieval runs for every substantive question, not just ones that
        # mention materials explicitly: most factual questions ("how many
        # types of X are there?") carry no lexical material reference, and
        # skipping retrieval for them guarantees a refusal despite indexed
        # evidence. PROJECT_GROUNDED *requires* evidence (insufficient →
        # refusal upstream); GENERAL_LEARNING grounds opportunistically and
        # otherwise answers generally. CLARIFICATION reuses conversation
        # history (a bare "why?" retrieves noise); UNSUPPORTED never arrives.
        if kind in (QuestionKind.PROJECT_GROUNDED, QuestionKind.GENERAL_LEARNING):
            embedding_service = self._ai().embedding_service(settings)
            retrieval = RetrievalService(self.session, embedding_service, settings)
            started = time.perf_counter()
            result = await retrieval.search(
                user_id=user_id,
                project_id=project.id,
                query=question,
                top_k=min(max(settings.tutor_max_retrieved_chunks, 1), 50),
                max_chunks=min(max(settings.tutor_max_retrieved_chunks, 1), 50),
                max_chars=min(max(settings.tutor_max_context_chars, 256), 200_000),
            )
            retrieval_latency_ms = int((time.perf_counter() - started) * 1000)
            insufficient = result.insufficient_evidence
            top_similarity = result.best_similarity
            if not insufficient:
                # Use the bounded context built by RetrievalService verbatim
                # (deduped, strongest-first, within max_chunks/max_chars):
                # result.results is the full threshold-filtered candidate
                # list, while result.citations is the budgeted subset —
                # formatting results directly would bypass the budget and
                # could show the model more chunks than we cite (or drop the
                # truncation of a single oversized chunk). Strip the outer
                # RAG delimiters here; build_tutor_prompt adds the single
                # tutor-level wrapper around this evidence.
                from app.ai.prompts import SOURCE_BEGIN, SOURCE_END

                evidence_text = _strip_rag_delimiters(
                    result.context.text, begin=SOURCE_BEGIN, end=SOURCE_END
                )
                citation_dicts = [
                    {
                        "chunk_id": str(c.chunk_id),
                        "document_id": str(c.document_id),
                        "material_id": str(c.material_id),
                        "material_name": c.material_name,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                    }
                    for c in result.citations
                ]
        from app.services.learning_context_service import LearningContextService

        persistent = LearningContextService(self.session).context_for_tutor(
            user_id=user_id, project_id=project.id
        )
        return LearningContext(
            project_name=project.name,
            learning_goal=project.learning_goal,
            target_outcome=project.target_outcome,
            difficulty=project.difficulty.value if project.difficulty is not None else None,
            persistent_context=persistent,
            history=history,
            concepts=concepts,
            mastery_estimates=self._relevant_mastery(
                user_id=user_id, project_id=project.id, concept_names=concepts
            ),
            evidence_text=evidence_text,
            has_evidence=bool(evidence_text.strip()),
            citation_dicts=citation_dicts,
            insufficient=insufficient,
            top_similarity=top_similarity,
            retrieval_latency_ms=retrieval_latency_ms,
        )

    def _relevant_mastery(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, concept_names: list[str]
    ) -> dict[str, float]:
        """Persisted mastery for the question-relevant concepts only (bounded
        by the concept cap upstream). Read-only: lookup failures degrade to
        no mastery rather than failing the tutor turn."""
        if not concept_names:
            return {}
        try:
            from app.repositories.knowledge import ConceptRepository
            from app.services.mastery_service import MasteryService

            concepts = ConceptRepository(self.session).all_for_project(project_id)
            by_name = {c.name: c.id for c in concepts}
            ids = [by_name[name] for name in concept_names if name in by_name]
            if not ids:
                return {}
            estimates = MasteryService(self.session, settings=self.settings).scores_for_concepts(
                user_id=user_id, project_id=project_id, concept_ids=ids
            )
            names = {c.id: c.name for c in concepts}
            return {names[cid]: score for cid, score in estimates.items() if cid in names}
        except Exception as e:  # noqa: BLE001 - tutor must survive mastery faults
            log.warning("tutor mastery lookup failed project=%s err=%s", project_id, e)
            return {}

    def _relevant_concepts(self, *, project_id: uuid.UUID, question: str, limit: int) -> list[str]:
        """Deterministic project-scoped ranking: token overlap with the
        question, ties broken by name. Never leaves the project."""
        rows = self.session.execute(
            sa.select(Concept.name)
            .where(Concept.project_id == project_id)
            .order_by(Concept.name)
            .limit(200)
        ).all()
        query_tokens = set(re.findall(r"[a-z]{3,}", question.lower()))
        if not query_tokens:
            return [row[0] for row in rows[:limit]]
        scored: list[tuple[int, str, str]] = []
        for (name,) in rows:
            overlap = len(query_tokens & set(re.findall(r"[a-z]{3,}", name.lower())))
            scored.append((-overlap, name.lower(), name))
        scored.sort()
        ranked = [name for overlap, _, name in scored if overlap < 0] or [
            name for _, _, name in scored
        ]
        return ranked[:limit]

    # ---------------------------------------------------------- generation

    async def _call_model(
        self,
        *,
        project: Project,
        conversation: Conversation,
        context: LearningContext,
        question: str,
    ):
        """Single model call with one bounded retry on transient failures.
        Returns a namespace with validated output fields."""
        from types import SimpleNamespace

        settings = self.settings
        system, user_prompt = build_tutor_prompt(
            project_name=context.project_name,
            learning_goal=context.learning_goal,
            target_outcome=context.target_outcome,
            difficulty=context.difficulty,
            concepts=context.concepts,
            history=context.history,
            evidence_text=context.evidence_text,
            has_evidence=context.has_evidence,
            question=question,
            mastery=context.mastery_estimates or None,
            persistent_context=context.persistent_context or "",
        )
        chat = self._ai().tutor_chat(settings)
        provider_name = getattr(chat, "name", "groq")
        model_name = settings.groq_model_tutor
        last_error: Exception | None = None
        for attempt in range(settings.tutor_max_retries + 1):
            started = time.perf_counter()
            try:
                raw = await chat.chat_json(
                    system=system,
                    user=user_prompt,
                    model=model_name,
                    max_tokens=settings.tutor_max_response_tokens,
                )
                output = TutorStructuredOutput.model_validate(raw)
                latency_ms = int((time.perf_counter() - started) * 1000)
                usage = output_usage(raw)
                log_ai_call(
                    provider=provider_name,
                    model=model_name,
                    operation="tutor",
                    latency_ms=latency_ms,
                    status="ok",
                    input_tokens=usage[0],
                    output_tokens=usage[1],
                    project_id=project.id,
                    conversation_id=conversation.id,
                    retrieved_chunk_count=len(context.citation_dicts),
                )
                return SimpleNamespace(
                    answer=output.answer,
                    grounded=bool(output.grounded),
                    needs_clarification=output.needs_clarification,
                    model_name=model_name,
                    provider=provider_name,
                    latency_ms=latency_ms,
                    input_tokens=usage[0],
                    output_tokens=usage[1],
                )
            except AITransientError as e:
                last_error = e
                log_ai_call(
                    provider=provider_name,
                    model=model_name,
                    operation="tutor",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    status="retry" if attempt < settings.tutor_max_retries else "failed",
                    error_type=type(e).__name__,
                    project_id=project.id,
                    conversation_id=conversation.id,
                    retrieved_chunk_count=len(context.citation_dicts),
                )
                if attempt < settings.tutor_max_retries:
                    await asyncio.sleep(min(8.0, 1.0 * (2**attempt)))
            except TutorGenerationFailed as e:
                from app.services.ai_usage_service import AiUsageService

                AiUsageService(self.session).record(
                    feature="tutor",
                    provider=provider_name,
                    model=model_name,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    user_id=conversation.user_id,
                    project_id=project.id,
                    success=False,
                    error_type=type(e).__name__,
                )
                raise
            except Exception as e:  # noqa: BLE001 - malformed output etc.
                raise TutorGenerationFailed(
                    f"Tutor model output invalid: {type(e).__name__}."
                ) from e
        assert last_error is not None
        raise ServiceUnavailableError(
            "Tutor is temporarily unavailable, please retry."
        ) from last_error

    @transactional
    def _persist_assistant(
        self,
        *,
        user_id: uuid.UUID,
        project: Project,
        conversation: Conversation,
        user_message: Message,
        answer: str,
        citations: list[dict],
        grounded: bool,
        insufficient_evidence: bool,
        kind: QuestionKind,
        model: str | None,
        provider: str | None,
        latency_ms: int,
        retrieval_count: int,
        needs_clarification: bool = False,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> TutorExchange:
        assistant = self.messages.append(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=answer,
            model=model,
            provider=provider,
        )
        assistant.latency_ms = latency_ms
        assistant.retrieval_count = retrieval_count
        assistant.citations = citations
        assistant.tutor_metadata = {
            "question_kind": kind.value,
            "grounded": grounded,
            "insufficient_evidence": insufficient_evidence,
            "needs_clarification": needs_clarification,
        }
        self.session.flush()
        if model is not None and provider is not None:
            # Real provider call happened (deterministic unsupported /
            # insufficient paths pass model=None and record nothing).
            from app.services.ai_usage_service import AiUsageService

            AiUsageService(self.session).record(
                feature="tutor",
                provider=provider,
                model=model,
                latency_ms=latency_ms,
                user_id=user_id,
                project_id=project.id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                request_id=user_message.request_key,
            )
        self.events.append(
            event_type=EventType.TUTOR_RESPONSE,
            user_id=user_id,
            project_id=project.id,
            entity_type="message",
            entity_id=assistant.id,
            payload={
                "conversation_id": str(conversation.id),
                "grounded": grounded,
                "citations": len(citations),
                "kind": kind.value,
            },
        )
        return TutorExchange(
            user_message=user_message,
            assistant_message=assistant,
            citations=citations,
            grounded=grounded,
            insufficient_evidence=insufficient_evidence,
        )


def output_usage(raw: dict) -> tuple[int | None, int | None]:
    """Token counts only when the provider actually reports them."""
    usage = raw.get("usage") if isinstance(raw, dict) else None
    if not isinstance(usage, dict):
        return None, None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return (
        prompt if isinstance(prompt, int) else None,
        completion if isinstance(completion, int) else None,
    )
