"""Assessment endpoints: quizzes, attempts, answers, completion, results.

Every route verifies authenticated user -> owned project -> owned quiz /
attempt / assessment. Cross-tenant access returns 404 without disclosure.
Business logic lives in AssessmentService; routes only map HTTP to service
calls. Pre-answer payloads are learner-safe (no correct answers, references,
or evaluator internals); post-answer payloads reveal feedback only for the
answered question.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_owned_project
from app.db.session import get_db
from app.models.learning import Project
from app.schemas.assessment import (
    AnswerResult,
    AnswerState,
    AnswerSubmit,
    AssessmentSummaryRead,
    AttemptDetailRead,
    AttemptQuestionView,
    AttemptRead,
    CompleteResult,
    ConceptPerformanceRead,
    LearnerConcept,
    LearnerOption,
    LearnerQuestion,
    LearnerSource,
    QuizCreate,
    QuizDetailRead,
    QuizRead,
)
from app.services.assessment_service import AssessmentService

router = APIRouter(prefix="/projects", tags=["assessment"])

SessionDep = Annotated[Session, Depends(get_db)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]


def _to_quiz_read(quiz, *, question_count: int = 0) -> QuizRead:
    return QuizRead(
        id=quiz.id,
        project_id=quiz.project_id,
        title=quiz.title,
        status=quiz.status,
        difficulty=quiz.difficulty,
        question_count=question_count,
        created_at=quiz.created_at,
    )


def _to_learner_question(view: dict) -> LearnerQuestion:
    return LearnerQuestion(
        question_id=view["question_id"],
        type=view["type"],
        prompt=view["prompt"],
        options=[LearnerOption(**o) for o in view.get("options", [])],
        position=view["position"],
        points=view.get("points", 1.0),
        difficulty=view.get("difficulty"),
        concepts=[LearnerConcept(**c) for c in view.get("concepts", [])],
        sources=[LearnerSource(**s) for s in view.get("sources", [])],
    )


def _to_attempt_detail(detail: dict) -> AttemptDetailRead:
    attempt = detail["attempt"]
    questions = []
    for view in detail["questions"]:
        base = _to_learner_question(view).model_dump()
        questions.append(AttemptQuestionView(**base, answer=AnswerState(**view["answer"])))
    return AttemptDetailRead(attempt=AttemptRead.model_validate(attempt), questions=questions)


def _to_complete(result) -> CompleteResult:
    return CompleteResult(
        assessment_id=result.assessment_id,
        quiz_attempt_id=result.quiz_attempt_id,
        quiz_id=result.quiz_id,
        total_questions=result.total_questions,
        answered_count=result.answered_count,
        correct_count=result.correct_count,
        partial_count=result.partial_count,
        incorrect_count=result.incorrect_count,
        score=result.score,
        concept_results=[
            ConceptPerformanceRead(
                concept_id=c.concept_id,
                concept_name=c.concept_name,
                questions_seen=c.questions_seen,
                correct_count=c.correct_count,
                partial_count=c.partial_count,
                incorrect_count=c.incorrect_count,
                normalized_score=c.normalized_score,
                recent=list(c.recent),
            )
            for c in result.concept_results
        ],
    )


@router.post("/{project_id}/quizzes", status_code=status.HTTP_201_CREATED)
async def create_quiz(
    project: OwnedProject, user: CurrentUser, session: SessionDep, body: QuizCreate
):
    """Generate a READY quiz synchronously (bounded work; see service notes).
    Replays return the original quiz with 200."""
    from fastapi.responses import JSONResponse

    service = AssessmentService(session)
    quiz, created = await service.create_quiz(
        user_id=user.id,
        project_id=project.id,
        question_count=body.question_count,
        difficulty=body.difficulty,
        focus_concepts=body.focus_concepts,
        question_types=body.question_types,
        title=body.title,
        client_request_key=body.client_request_key,
    )
    views = service.quiz_questions_view(quiz.id)
    payload = QuizDetailRead(
        quiz=_to_quiz_read(quiz, question_count=len(views)),
        questions=[_to_learner_question(v) for v in views],
    ).model_dump(mode="json")
    return JSONResponse(status_code=201 if created else 200, content=payload)


@router.get("/{project_id}/quizzes", response_model=list[QuizRead])
def list_quizzes(project: OwnedProject, user: CurrentUser, session: SessionDep):
    service = AssessmentService(session)
    quizzes = service.list_quizzes(user_id=user.id, project_id=project.id)
    counts = service.quiz_question_counts(project.id)
    return [_to_quiz_read(q, question_count=counts.get(q.id, 0)) for q in quizzes]


@router.get("/{project_id}/quizzes/{quiz_id}", response_model=QuizDetailRead)
def get_quiz(quiz_id: uuid.UUID, project: OwnedProject, user: CurrentUser, session: SessionDep):
    service = AssessmentService(session)
    quiz = service.get_quiz(user_id=user.id, project_id=project.id, quiz_id=quiz_id)
    views = service.quiz_questions_view(quiz.id)
    return QuizDetailRead(
        quiz=_to_quiz_read(quiz, question_count=len(views)),
        questions=[_to_learner_question(v) for v in views],
    )


@router.post("/{project_id}/quizzes/{quiz_id}/attempts")
async def start_attempt(
    quiz_id: uuid.UUID, project: OwnedProject, user: CurrentUser, session: SessionDep
):
    """Start or resume the IN_PROGRESS attempt. 201 on create, 200 on resume."""
    from fastapi.responses import JSONResponse

    service = AssessmentService(session)
    attempt, created = await service.start_attempt(
        user_id=user.id, project_id=project.id, quiz_id=quiz_id
    )
    payload = _to_attempt_detail(service.attempt_detail_view(attempt)).model_dump(mode="json")
    return JSONResponse(status_code=201 if created else 200, content=payload)


@router.get("/{project_id}/attempts/{attempt_id}", response_model=AttemptDetailRead)
def get_attempt(
    attempt_id: uuid.UUID, project: OwnedProject, user: CurrentUser, session: SessionDep
):
    service = AssessmentService(session)
    attempt = service.get_attempt(user_id=user.id, project_id=project.id, attempt_id=attempt_id)
    return _to_attempt_detail(service.attempt_detail_view(attempt))


@router.post("/{project_id}/attempts/{attempt_id}/answers", response_model=AnswerResult)
async def submit_answer(
    attempt_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    body: AnswerSubmit,
):
    service = AssessmentService(session)
    result = await service.submit_answer(
        user_id=user.id,
        project_id=project.id,
        attempt_id=attempt_id,
        question_id=body.question_id,
        answer=body.answer,
    )
    return AnswerResult(**result)


@router.post("/{project_id}/attempts/{attempt_id}/complete", response_model=CompleteResult)
async def complete_attempt(
    attempt_id: uuid.UUID, project: OwnedProject, user: CurrentUser, session: SessionDep
):
    service = AssessmentService(session)
    result = await service.complete_attempt(
        user_id=user.id, project_id=project.id, attempt_id=attempt_id
    )
    return _to_complete(result)


@router.get("/{project_id}/assessments", response_model=list[AssessmentSummaryRead])
def list_assessments(project: OwnedProject, user: CurrentUser, session: SessionDep):
    service = AssessmentService(session)
    return [
        AssessmentSummaryRead(**row)
        for row in service.list_assessments(user_id=user.id, project_id=project.id)
    ]


@router.get("/{project_id}/assessments/{assessment_id}", response_model=CompleteResult)
def get_assessment(
    assessment_id: uuid.UUID, project: OwnedProject, user: CurrentUser, session: SessionDep
):
    service = AssessmentService(session)
    result = service.get_assessment(
        user_id=user.id, project_id=project.id, assessment_id=assessment_id
    )
    return _to_complete(result)
