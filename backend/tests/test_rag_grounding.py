"""RAG grounding regression suite: the Tutor must answer paraphrased factual
questions from project evidence instead of refusing.

Root cause this guards: ``classify_intent`` routes questions without explicit
material keywords ("how many types of classifications are there?") to
GENERAL_LEARNING, and the Tutor used to skip retrieval entirely for that
kind — guaranteeing an insufficient-evidence refusal despite indexed,
above-threshold evidence. Retrieval now runs for every substantive question;
PROJECT_GROUNDED still *requires* evidence while GENERAL_LEARNING grounds
opportunistically.

All retrieval here uses the deterministic fake embedding provider
(bag-of-words unit vectors): paraphrases sharing content words score above
the 0.3 threshold, disjoint text scores near zero. No live providers."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.orm import Session

from app.ai.base import EmbedRequest
from app.ai.errors import EmbeddingDimensionMismatch
from app.ai.fakes import DeterministicEmbeddingProvider, FakeChatProvider
from app.ai.service import AIService
from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.documents.pipeline import PipelineConfig, process_pdf
from app.models.enums import MaterialStatus
from app.models.materials import Document, DocumentChunk
from app.rag.retrieval import RetrievalService, build_rag_context
from app.repositories.materials import MaterialRepository
from app.services.tutor_service import QuestionKind, TutorService, classify_intent
from tests.conftest import make_project, make_user
from tests.pdf_fixtures import make_text_pdf

CHUNK_TEXT = (
    "Classification tasks come in three types: binary classification, "
    "multiclass classification, and multilabel classification. Each type "
    "suits a different prediction problem in supervised learning."
)
UNRELATED = "Photosynthesis converts sunlight into chemical energy in leaves."


def _fake_settings(**kwargs) -> Settings:
    kwargs.setdefault("test_fake_ai", True)
    return Settings(**kwargs)


def _fake_ai() -> AIService:
    return AIService(
        chat_provider=FakeChatProvider(),
        embedding_provider=DeterministicEmbeddingProvider(dimensions=768),
    )


def _seed(session: Session, texts: list[str], owner=None):
    owner = owner or make_user(session)
    project = make_project(session, owner)
    mat = MaterialRepository(session).create(project_id=project.id, name="Doc")
    mat.status = MaterialStatus.READY
    session.flush()
    doc = Document(material_id=mat.id, project_id=project.id, page_count=len(texts))
    session.add(doc)
    session.flush()
    provider = DeterministicEmbeddingProvider(dimensions=768)
    for i, text in enumerate(texts):
        vec = asyncio.run(provider.embed(EmbedRequest(texts=[text]))).embeddings[0]
        session.add(
            DocumentChunk(
                document_id=doc.id,
                project_id=project.id,
                chunk_index=i,
                content=text,
                page_start=7,
                page_end=7,
                embedding=list(vec),
            )
        )
    session.commit()
    return owner, project, mat


def _service(session: Session) -> TutorService:
    return TutorService(session, settings=_fake_settings(), ai_service=_fake_ai())


def _send(session, owner, project, content: str):
    svc = _service(session)
    conv = svc.create_conversation(user_id=owner.id, project_id=project.id)
    return asyncio.run(
        svc.send_message(
            user_id=owner.id,
            project_id=project.id,
            conversation_id=conv.id,
            content=content,
        )
    )


# TEST 1 + 10: the exact failing question (no material keywords) is answered
# from evidence with an application-built citation. Live production evidence:
# Gemini retrieval for this query returns the binary/multiclass/multilabel
# chunk at similarity 0.616 (threshold 0.3). The fake provider below is
# bag-of-words without morphology, so the seeded chunk uses the plural forms
# a real slide would also contain; routing (not wording) is what regressed.
PLURAL_CHUNK = (
    "There are three classifications types: binary classifications, "
    "multiclass classifications, and multilabel classifications. Each type "
    "suits a different prediction problem you will meet in this course."
)


def test_paraphrased_question_grounds_with_citation(session: Session) -> None:
    owner, project, _ = _seed(session, [PLURAL_CHUNK, UNRELATED])
    exchange = _send(session, owner, project, "how many types of classifications are there?")
    assert (
        classify_intent("how many types of classifications are there?", has_history=False)
        is QuestionKind.GENERAL_LEARNING
    )  # the routing that used to skip retrieval
    assert exchange.grounded is True
    assert exchange.insufficient_evidence is False
    assert len(exchange.citations) == 1
    assert exchange.citations[0]["page_start"] == 7
    assert exchange.citations[0]["material_name"] == "Doc"
    assert "classification" in exchange.assistant_message.content.lower()


# TEST 2: different wording and word order, same meaning, still retrieves.
def test_alternate_paraphrase_retrieves(session: Session) -> None:
    owner, project, _ = _seed(session, [CHUNK_TEXT, UNRELATED])
    exchange = _send(
        session, owner, project, "What types of classification tasks exist in supervised learning?"
    )
    assert exchange.grounded is True
    assert exchange.citations[0]["page_start"] == 7


# TEST 3: page provenance survives the full path.
def test_citation_page_provenance(session: Session) -> None:
    owner, project, _ = _seed(session, [CHUNK_TEXT])
    exchange = _send(session, owner, project, "Tell me about classification types")
    assert exchange.citations
    assert exchange.citations[0]["page_start"] == 7
    assert exchange.citations[0]["page_end"] == 7
    assert uuid.UUID(exchange.citations[0]["chunk_id"])


# TEST 4: project isolation holds for the new retrieval path.
def test_other_project_evidence_never_leaks(session: Session) -> None:
    owner_a, project_a, _ = _seed(session, [CHUNK_TEXT])
    owner_b = make_user(session)
    project_b = make_project(session, owner_b)
    exchange = _send(session, owner_b, project_b, "how many types of classifications are there?")
    assert exchange.grounded is False
    assert exchange.citations == []
    # And direct cross-project retrieval is non-disclosing.
    settings = _fake_settings()
    svc = RetrievalService(session, _fake_ai().embedding_service(settings), settings)
    with pytest.raises(NotFoundError):
        asyncio.run(
            svc.search(user_id=owner_b.id, project_id=project_a.id, query="classification types")
        )


# TEST 5a: genuinely unrelated + explicit material reference still refuses
# without consulting the model.
def test_unrelated_grounded_question_still_refuses(session: Session) -> None:
    owner, project, _ = _seed(session, [CHUNK_TEXT])
    svc = _service(session)
    conv = svc.create_conversation(user_id=owner.id, project_id=project.id)
    calls: list[str] = []

    real_fake = FakeChatProvider()

    class CountingChat:
        name = "counting"

        async def chat_json(  # type: ignore[no-untyped-def]
            self, *, system: str, user: str, model: str, max_tokens: int | None = None
        ):
            calls.append(user)
            return await real_fake.chat_json(system=system, user=user, model=model)

    counting = AIService(
        chat_provider=CountingChat(),  # type: ignore[arg-type]
        embedding_provider=DeterministicEmbeddingProvider(dimensions=768),
    )
    svc2 = TutorService(session, settings=_fake_settings(), ai_service=counting)
    exchange = asyncio.run(
        svc2.send_message(
            user_id=owner.id,
            project_id=project.id,
            conversation_id=conv.id,
            content="What does the PDF say about quantum tunneling?",
        )
    )
    assert exchange.insufficient_evidence is True
    assert exchange.grounded is False
    assert calls == []


# TEST 5b: unrelated general question answers generally, never grounded.
def test_unrelated_general_question_answers_without_citation(session: Session) -> None:
    owner, project, _ = _seed(session, [CHUNK_TEXT])
    exchange = _send(session, owner, project, "What is the capital of Assyria?")
    assert exchange.grounded is False
    assert exchange.citations == []
    assert exchange.insufficient_evidence is False


# TEST 6: chunks without embeddings are invisible to retrieval (knowledge
# repair path owns backfill; retrieval must never match NULL vectors).
def test_unembedded_chunks_excluded(session: Session) -> None:
    owner, project, _ = _seed(session, [CHUNK_TEXT])
    doc = session.query(Document).filter_by(project_id=project.id).one()
    session.add(
        DocumentChunk(
            document_id=doc.id,
            project_id=project.id,
            chunk_index=99,
            content=CHUNK_TEXT,
            page_start=7,
            page_end=7,
            embedding=None,
        )
    )
    session.commit()
    settings = _fake_settings()
    svc = RetrievalService(session, _fake_ai().embedding_service(settings), settings)
    result = asyncio.run(
        svc.search(user_id=owner.id, project_id=project.id, query="classification types", top_k=10)
    )
    assert all(r.text is not None for r in result.results)
    assert len(result.results) == 1  # the NULL-embedding twin is excluded


# TEST 8: wrong-width vectors are rejected, never persisted silently.
def test_embedding_dimension_mismatch_rejected() -> None:
    from app.ai.base import EmbedResponse
    from app.ai.embeddings import EmbeddingService

    class WrongWidth:
        name = "wrong"

        async def embed(self, request):  # type: ignore[no-untyped-def]
            return EmbedResponse(embeddings=[[0.1] * 64], model=request.model)

    svc = EmbeddingService(WrongWidth(), model="m", dimensions=768)  # type: ignore[arg-type]
    with pytest.raises(EmbeddingDimensionMismatch):
        asyncio.run(svc.embed_texts(["hello world, this is a real sentence"]))


# TEST 9: one centralized config serves document and query embeddings.
def test_single_embedding_config_for_docs_and_queries() -> None:
    settings = _fake_settings()
    assert settings.google_embedding_model
    assert settings.embedding_dimensions == 768
    svc = _fake_ai().embedding_service(settings)
    assert svc.model == settings.google_embedding_model
    assert svc.dimensions == settings.embedding_dimensions
    doc_vecs = asyncio.run(svc.embed_texts([CHUNK_TEXT]))
    query_vec = asyncio.run(svc.embed_query("classification types"))
    assert len(doc_vecs[0]) == len(query_vec) == 768


# TEST 11: truncation keeps the strongest evidence, never drops it.
def test_context_truncation_preserves_strongest(session: Session) -> None:
    owner, project, _ = _seed(session, [CHUNK_TEXT, UNRELATED])
    settings = _fake_settings()
    svc = RetrievalService(session, _fake_ai().embedding_service(settings), settings)
    result = asyncio.run(
        svc.search(user_id=owner.id, project_id=project.id, query="classification types", top_k=10)
    )
    assert len(result.results) >= 1
    strongest = result.results[0]
    tiny = build_rag_context(result.results, max_chunks=8, max_chars=120)
    assert tiny.truncated is True
    assert tiny.chunk_count >= 1
    assert tiny.citations[0].chunk_id == strongest.chunk_id
    assert "classification" in tiny.text.lower()


# TEST 12: extraction preserves the relevant PDF text into chunks.
def test_extraction_preserves_relevant_text() -> None:
    sentence = (
        "Classification tasks come in three types: binary classification, "
        "multiclass classification, and multilabel classification."
    )
    pdf = make_text_pdf([sentence + " " + sentence])
    result = process_pdf(pdf, PipelineConfig(), None.__class__ and _null_provider())
    body = " ".join(c.content for c in result.chunks)
    assert "multilabel classification" in body


def _null_provider():
    from app.documents.ocr import NullOcrProvider

    return NullOcrProvider()


# ------------------------------------------------------- admin RAG diagnostic


@pytest.fixture()
def api_client(session: Session, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core import config as config_module
    from app.db.session import get_db
    from app.main import create_app

    monkeypatch.setenv("TEST_FAKE_AI", "true")
    config_module.get_settings.cache_clear()
    app = create_app()

    def _override():  # type: ignore[no-untyped-def]
        yield session

    app.dependency_overrides[get_db] = _override
    yield TestClient(app, raise_server_exceptions=False)
    config_module.get_settings.cache_clear()


def _register(api_client, email: str) -> dict:
    res = api_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass123", "display_name": "T"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_admin_rag_diagnose_returns_scores_not_vectors(
    session: Session, api_client, monkeypatch
) -> None:
    from app.core import config as config_module

    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com")
    config_module.get_settings.cache_clear()
    owner, project, _ = _seed(session, [CHUNK_TEXT, UNRELATED])
    admin = _register(api_client, "boss@example.com")
    assert admin["user"]["role"] == "admin"

    res = api_client.get(
        "/api/v1/admin/rag/diagnose",
        params={"project_id": str(project.id), "query": "classification types", "top_k": 5},
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["query"] == "classification types"
    assert body["project_id"] == str(project.id)
    assert body["embedding_dimension"] == 768
    assert body["embedding_model"]
    assert body["retrieval_count"] >= 1
    assert body["best_similarity"] is not None and body["best_similarity"] >= 0.3
    assert body["insufficient_evidence"] is False
    first = body["results"][0]
    assert first["page_start"] == 7
    assert first["material_name"] == "Doc"
    assert "classification" in first["text_preview"].lower()
    # No vectors, no secrets anywhere in the payload.
    blob = res.text
    assert 'embedding":' not in blob.replace("embedding_model", "").replace(
        "embedding_dimension", ""
    )
    assert "SecurePass123" not in blob


def test_admin_rag_diagnose_unknown_project_404(session: Session, api_client, monkeypatch) -> None:
    from app.core import config as config_module

    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com")
    config_module.get_settings.cache_clear()
    admin = _register(api_client, "boss@example.com")
    res = api_client.get(
        "/api/v1/admin/rag/diagnose",
        params={"project_id": str(uuid.uuid4()), "query": "anything"},
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert res.status_code == 404


def test_learner_denied_rag_diagnose(session: Session, api_client) -> None:
    owner, project, _ = _seed(session, [CHUNK_TEXT])
    learner = _register(api_client, "learner@example.com")
    assert learner["user"]["role"] == "learner"
    res = api_client.get(
        "/api/v1/admin/rag/diagnose",
        params={"project_id": str(project.id), "query": "classification"},
        headers={"Authorization": f"Bearer {learner['access_token']}"},
    )
    assert res.status_code == 403


# TEST 13: general question with weak retrieval the model declines →
# general answer, no citations (no noise attached).
def test_general_mode_model_decline_drops_citations(session: Session) -> None:
    owner, project, _ = _seed(session, [CHUNK_TEXT, UNRELATED])
    real_fake = FakeChatProvider()

    class Humble:
        name = "humble"

        async def chat_json(  # type: ignore[no-untyped-def]
            self, *, system: str, user: str, model: str, max_tokens: int | None = None
        ):
            out = await real_fake.chat_json(system=system, user=user, model=model)
            out["grounded"] = False
            out["answer"] = "A general explanation from background knowledge."
            return out

    ai = AIService(
        chat_provider=Humble(),  # type: ignore[arg-type]
        embedding_provider=DeterministicEmbeddingProvider(dimensions=768),
    )
    svc = TutorService(session, settings=_fake_settings(), ai_service=ai)
    conv = svc.create_conversation(user_id=owner.id, project_id=project.id)
    exchange = asyncio.run(
        svc.send_message(
            user_id=owner.id,
            project_id=project.id,
            conversation_id=conv.id,
            content="What types of classification tasks exist in supervised learning?",
        )
    )
    assert exchange.grounded is False
    assert exchange.citations == []
    assert exchange.insufficient_evidence is False
    assert "background knowledge" in exchange.assistant_message.content


# TEST 14: split embedding widths are rejected at startup (single source of
# truth for document/query dimensions).
def test_split_embedding_dimensions_rejected() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        Settings(test_fake_ai=True, embedding_dimensions=768, google_embedding_dimensions=0)
    with pytest.raises(pydantic.ValidationError):
        Settings(test_fake_ai=True, embedding_dimensions=768, google_embedding_dimensions=3072)


# TEST 15: Tutor evidence reuses the bounded RAG context (dedup + budget),
# so citations and model-visible evidence stay 1:1 and strongest-first.
def test_tutor_evidence_matches_bounded_context(session: Session) -> None:
    owner, project, _ = _seed(session, [CHUNK_TEXT, CHUNK_TEXT.upper(), UNRELATED])
    svc = TutorService(
        session, settings=_fake_settings(tutor_max_context_chars=300), ai_service=_fake_ai()
    )
    conv = svc.create_conversation(user_id=owner.id, project_id=project.id)
    exchange = asyncio.run(
        svc.send_message(
            user_id=owner.id,
            project_id=project.id,
            conversation_id=conv.id,
            content="What types of classification tasks exist in supervised learning?",
        )
    )
    assert exchange.grounded is True
    # Bounded: at most the configured budget reaches the model prompt path
    # (the duplicate collapses, the unrelated chunk is cut by the budget).
    assert len(exchange.citations) <= 2
    assert exchange.citations[0]["page_start"] == 7
    # Evidence and citations agree on the strongest chunk first.
    settings = _fake_settings()
    retrieval = RetrievalService(session, _fake_ai().embedding_service(settings), settings)
    result = asyncio.run(
        retrieval.search(
            user_id=owner.id,
            project_id=project.id,
            query="What types of classification tasks exist in supervised learning?",
            top_k=10,
        )
    )
    assert result.citations[0].chunk_id == uuid.UUID(exchange.citations[0]["chunk_id"])


# Retrieval guardrails (knowledge-readiness UX must never weaken these):
# the similarity threshold stays 0.3 and below-threshold retrieval still
# yields explicit insufficient evidence.
def test_retrieval_threshold_not_weakened(session: Session) -> None:
    from app.core.config import Settings as AppSettings

    assert AppSettings(test_fake_ai=True).rag_similarity_threshold == pytest.approx(0.3)
    owner, project, _ = _seed(session, [CHUNK_TEXT])
    settings = _fake_settings()
    svc = RetrievalService(session, _fake_ai().embedding_service(settings), settings)
    unrelated = asyncio.run(
        svc.search(user_id=owner.id, project_id=project.id, query="quantum tunneling neutrino mass")
    )
    assert unrelated.insufficient_evidence is True
    assert unrelated.results == []
