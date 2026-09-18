"""Domain-model persistence tests: constraints, relationships, defaults, cascades."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.assessment import (
    QuestionAttempt,
    QuestionConcept,
)
from app.models.enums import (
    AttemptStatus,
    ConceptRelationType,
    EventType,
    GrowthStatus,
    JobStatus,
    MasterySource,
    MaterialStatus,
    MessageRole,
    QuestionType,
)
from app.models.intelligence import Growth, Mastery, MasteryHistory
from app.models.knowledge import Concept, ConceptRelationship
from app.models.learning import Project
from app.models.materials import Document, DocumentChunk
from app.models.ops import Event
from app.repositories.assessments import (
    AssessmentRepository,
    AttemptRepository,
    QuestionRepository,
    QuizRepository,
)
from app.repositories.intelligence import (
    EventRepository,
    GrowthRepository,
    MasteryRepository,
    RecommendationRepository,
)
from app.repositories.knowledge import (
    ConceptRelationshipRepository,
    ConceptRepository,
    ConversationRepository,
    MessageRepository,
)
from app.repositories.materials import (
    ChunkRepository,
    DocumentRepository,
    MaterialRepository,
    ProcessingJobRepository,
)
from app.repositories.projects import ProjectRepository, SpaceRepository, UserRepository
from tests.conftest import make_project, make_space, make_user


def test_user_email_unique_and_normalized(session: Session) -> None:
    repo = UserRepository(session)
    repo.create(
        email="Alice@Example.COM ",
        password_hash="x",
        display_name="Alice",
    )
    session.commit()
    stored = repo.get_by_email("alice@example.com")
    assert stored is not None and stored.email == "alice@example.com"
    assert stored.created_at is not None and stored.updated_at is not None
    assert isinstance(stored.id, uuid.UUID)
    with pytest.raises(IntegrityError):
        repo.create(email="ALICE@example.com", password_hash="y", display_name="Dup")
        session.commit()


def test_space_ownership_and_project_hierarchy(session: Session) -> None:
    owner = make_user(session)
    space = make_space(session, owner, name="Physics")
    project = make_project(session, owner, space, name="Mechanics")

    assert project.space_id == space.id
    assert project.owner_id == owner.id  # denormalized at creation, consistent
    assert project.archived_at is None

    spaces, total = SpaceRepository(session).list_for_user(owner.id)
    assert total == 1 and spaces[0].id == space.id
    projects, total = ProjectRepository(session).list_for_space(space.id, owner.id)
    assert total == 1 and projects[0].id == project.id

    # Pagination is bounded.
    for i in range(4):
        SpaceRepository(session).create(owner_id=owner.id, name=f"S{i}")
    session.commit()
    page1, total = SpaceRepository(session).list_for_user(owner.id, page=1, page_size=2)
    assert total == 5 and len(page1) == 2

    # Deleting the user cascades through spaces and projects.
    session.delete(owner)
    session.commit()
    assert session.scalar(sa.select(sa.func.count()).select_from(Project)) == 0


def test_material_lifecycle_and_job(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    materials = MaterialRepository(session)
    mat = materials.create(
        project_id=project.id,
        name="Lecture 1",
        original_filename="l1.pdf",
        mime_type="application/pdf",
        file_size=1024,
    )
    session.commit()
    assert mat.status == MaterialStatus.QUEUED
    assert mat.retry_count == 0
    assert mat.type.value == "PDF"

    found = materials.get_for_project(mat.id, project.id)
    assert found is not None and found.id == mat.id

    jobs = ProcessingJobRepository(session)
    job = jobs.enqueue(
        job_type="document.process",
        project_id=project.id,
        material_id=mat.id,
        idempotency_key="idem-1",
    )
    session.commit()
    assert job.status == JobStatus.QUEUED
    assert len(jobs.get_pending_for_material(mat.id)) == 1
    with pytest.raises(IntegrityError):
        jobs.enqueue(job_type="document.process", idempotency_key="idem-1")
        session.commit()
    session.rollback()


def test_document_one_to_one_and_chunk_ordering(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    mat = MaterialRepository(session).create(project_id=project.id, name="Doc")
    session.flush()
    docs = DocumentRepository(session)
    doc = docs.add(Document(material_id=mat.id, project_id=project.id, page_count=10))
    session.commit()
    assert mat.document is not None and mat.document.id == doc.id
    with pytest.raises(IntegrityError):
        docs.add(Document(material_id=mat.id, project_id=project.id))
        session.commit()
    session.rollback()

    chunks = ChunkRepository(session)
    for i in range(3):
        chunks.add(
            DocumentChunk(
                document_id=doc.id, project_id=project.id, chunk_index=i, content=f"chunk {i}"
            )
        )
    session.commit()
    with pytest.raises(IntegrityError):
        chunks.add(
            DocumentChunk(document_id=doc.id, project_id=project.id, chunk_index=1, content="dup")
        )
        session.commit()
    session.rollback()
    ordered = chunks.list_for_document(doc.id, project.id)
    assert [c.chunk_index for c in ordered] == [0, 1, 2]


def test_concept_project_scoped_uniqueness(session: Session) -> None:
    owner = make_user(session)
    project_a = make_project(session, owner, name="A")
    project_b = make_project(session, owner, name="B")
    concepts = ConceptRepository(session)

    c1, created = concepts.get_or_create(project_id=project_a.id, name="Entropy")
    assert created is True
    session.commit()
    c1_again, created = concepts.get_or_create(project_id=project_a.id, name="  ENTROPY ")
    assert created is False and c1_again.id == c1.id  # normalized match

    # Same name in another project is fine.
    c2, created = concepts.get_or_create(project_id=project_b.id, name="Entropy")
    assert created is True
    session.commit()

    # Bypassing the repo still hits the DB constraint.
    with pytest.raises(IntegrityError):
        concepts.add(Concept(project_id=project_a.id, name="entropy", normalized_name="entropy"))
        session.commit()
    session.rollback()
    assert c1.normalized_name == "entropy"
    assert c2.project_id != c1.project_id


def test_concept_relationship_guards(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    other = make_project(session, owner, name="Other")
    concepts = ConceptRepository(session)
    a, _ = concepts.get_or_create(project_id=project.id, name="A")
    b, _ = concepts.get_or_create(project_id=project.id, name="B")
    c, _ = concepts.get_or_create(project_id=other.id, name="C")
    session.commit()

    rels = ConceptRelationshipRepository(session)
    with pytest.raises(ValueError):
        rels.link(
            project_id=project.id,
            source_id=a.id,
            target_id=a.id,
            relationship_type=ConceptRelationType.PREREQUISITE,
        )

    rels.link(
        project_id=project.id,
        source_id=a.id,
        target_id=b.id,
        relationship_type=ConceptRelationType.PREREQUISITE,
    )
    session.commit()
    with pytest.raises(IntegrityError):  # duplicate directional link
        rels.link(
            project_id=project.id,
            source_id=a.id,
            target_id=b.id,
            relationship_type=ConceptRelationType.PREREQUISITE,
        )
        session.commit()
    session.rollback()

    # Cross-project endpoints violate the composite foreign keys.
    with pytest.raises(IntegrityError):
        rels.link(
            project_id=project.id,
            source_id=a.id,
            target_id=c.id,
            relationship_type=ConceptRelationType.RELATED,
        )
        session.commit()
    session.rollback()
    assert session.scalar(sa.select(sa.func.count()).select_from(ConceptRelationship)) == 1


def test_conversation_message_history_bounded(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    convos = ConversationRepository(session)
    conv = convos.create(project_id=project.id, user_id=owner.id, title="Tutoring")
    session.commit()

    msgs = MessageRepository(session)
    for i in range(3):
        role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT
        msgs.append(conversation_id=conv.id, role=role, content=f"m{i}")
    session.commit()
    history = msgs.history(conv.id, limit=2)
    assert [m.content for m in history] == ["m1", "m2"]  # bounded, oldest first


def test_quiz_question_ordering_and_links(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    quizzes = QuizRepository(session)
    questions = QuestionRepository(session)
    quiz = quizzes.create(project_id=project.id, title="Quiz 1")
    q1 = questions.create(
        project_id=project.id,
        type=QuestionType.MCQ,
        prompt="2+2?",
        options=[{"key": "a", "text": "4"}],
        correct_answer="a",
    )
    q2 = questions.create(project_id=project.id, type=QuestionType.OPEN_ENDED, prompt="Explain.")
    session.commit()

    quizzes.add_question(quiz_id=quiz.id, question_id=q1.id, position=0)
    quizzes.add_question(quiz_id=quiz.id, question_id=q2.id, position=1)
    session.commit()
    ordered = quizzes.ordered_questions(quiz.id)
    assert [q.position for q in ordered] == [0, 1]

    with pytest.raises(IntegrityError):  # same question twice in one quiz
        quizzes.add_question(quiz_id=quiz.id, question_id=q1.id, position=5)
        session.commit()
    session.rollback()

    concept, _ = ConceptRepository(session).get_or_create(project_id=project.id, name="Arithmetic")
    session.flush()
    questions.link_concept(
        question_id=q1.id, concept_id=concept.id, project_id=project.id, is_primary=True
    )
    session.commit()
    assert session.scalar(sa.select(sa.func.count()).select_from(QuestionConcept)) == 1


def test_attempts_assessment_distinction(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    quiz = QuizRepository(session).create(project_id=project.id, title="Q")
    question = QuestionRepository(session).create(
        project_id=project.id, type=QuestionType.MCQ, prompt="?"
    )
    session.commit()

    attempts = AttemptRepository(session)
    attempt = attempts.start(quiz_id=quiz.id, user_id=owner.id, project_id=project.id)
    session.flush()
    attempts.answer(
        quiz_attempt_id=attempt.id, question_id=question.id, answer="a", is_correct=True, score=1.0
    )
    session.commit()
    assert attempt.status == AttemptStatus.IN_PROGRESS

    assessments = AssessmentRepository(session)
    assessment = assessments.create(
        project_id=project.id, user_id=owner.id, quiz_attempt_id=attempt.id
    )
    session.flush()
    assessments.complete(assessment, score=82.5)
    session.commit()
    assert assessment.score == 82.5

    # One assessment per attempt; question answers belong to the attempt.
    with pytest.raises(IntegrityError):
        assessments.create(project_id=project.id, user_id=owner.id, quiz_attempt_id=attempt.id)
        session.commit()
    session.rollback()
    with pytest.raises(IntegrityError):  # one answer per question per attempt
        attempts.answer(quiz_attempt_id=attempt.id, question_id=question.id, answer="b")
        session.commit()
    session.rollback()
    assert session.scalar(sa.select(sa.func.count()).select_from(QuestionAttempt)) == 1


def test_mastery_unique_triple_and_bounds(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    concept, _ = ConceptRepository(session).get_or_create(project_id=project.id, name="Gravity")
    session.commit()

    mastery_repo = MasteryRepository(session)
    mastery, history = mastery_repo.record_observation(
        user_id=owner.id,
        project_id=project.id,
        concept_id=concept.id,
        score=70.0,
        confidence=0.8,
        source=MasterySource.QUIZ,
    )
    session.commit()
    assert mastery.score == 70.0
    assert history.mastery_id == mastery.id  # history appended, mastery updated

    mastery_repo.record_observation(
        user_id=owner.id,
        project_id=project.id,
        concept_id=concept.id,
        score=80.0,
        source=MasterySource.ASSESSMENT,
    )
    session.commit()
    assert session.scalar(sa.select(sa.func.count()).select_from(Mastery)) == 1
    assert session.scalar(sa.select(sa.func.count()).select_from(MasteryHistory)) == 2

    with pytest.raises(IntegrityError):  # score out of 0-100 bounds
        mastery_repo.record_observation(
            user_id=owner.id,
            project_id=project.id,
            concept_id=concept.id,
            score=101.0,
            source=MasterySource.SYSTEM,
        )
        session.commit()
    session.rollback()

    growth = GrowthRepository(session).refresh(
        user_id=owner.id,
        project_id=project.id,
        concept_id=concept.id,
        status=GrowthStatus.IMPROVING,
        change_score=10.0,
    )
    session.commit()

    assert growth.status == GrowthStatus.IMPROVING
    again = GrowthRepository(session).refresh(
        user_id=owner.id,
        project_id=project.id,
        concept_id=concept.id,
        status=GrowthStatus.STABLE,
    )
    session.commit()
    assert again.id == growth.id  # in-place refresh, no duplicate row
    assert session.scalar(sa.select(sa.func.count()).select_from(Growth)) == 1


def test_recommendation_links_and_survival(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    concept, _ = ConceptRepository(session).get_or_create(project_id=project.id, name="Waves")
    mat = MaterialRepository(session).create(project_id=project.id, name="Ch. 3")
    session.commit()

    recs = RecommendationRepository(session)
    from app.models.enums import RecommendationStatus, RecommendationType

    rec = recs.create(
        project_id=project.id,
        user_id=owner.id,
        type=RecommendationType.REVIEW_CONCEPT,
        title="Review waves",
        concept_id=concept.id,
        material_id=mat.id,
        reason="Mastery below 60",
        priority=5,
    )
    session.commit()
    assert rec.status == RecommendationStatus.ACTIVE

    active, total = recs.list_active(project.id, owner.id)
    assert total == 1 and active[0].id == rec.id

    # Deleting the concept nulls the link instead of killing the recommendation.
    session.delete(concept)
    session.commit()
    session.refresh(rec)
    assert rec.concept_id is None
    assert rec.material_id == mat.id


def test_events_append_only(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    events = EventRepository(session)
    # Service-emitted lifecycle event from make_project above.
    existing, _ = events.list_for_project(project.id)
    assert {e.event_type for e in existing} == {EventType.PROJECT_CREATED}
    events.append(event_type=EventType.TUTOR_MESSAGE, user_id=owner.id, project_id=project.id)
    session.commit()

    items, total = events.list_for_project(project.id)
    assert total == 2
    by_type = {e.event_type: e for e in items}
    assert by_type[EventType.PROJECT_CREATED].payload["name"] == project.name
    assert by_type[EventType.TUTOR_MESSAGE].payload is None
    assert "updated_at" not in Event.__mapper__.attrs.keys()  # never updated
