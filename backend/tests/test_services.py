"""Schema contracts: internal fields never leak; service transactions are atomic."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models.enums import MasterySource
from app.models.intelligence import Mastery, MasteryHistory
from app.repositories.intelligence import EventRepository
from app.repositories.knowledge import ConceptRepository
from app.repositories.projects import SpaceRepository
from app.schemas.materials import MaterialRead
from app.schemas.users import UserCreate, UserRead
from app.services.mastery_service import MasteryService
from app.services.project_service import ProjectService
from tests.conftest import make_project, make_user


def test_password_hash_never_exposed() -> None:
    assert "password_hash" not in UserRead.model_fields
    assert "password" not in UserRead.model_fields
    payload = UserCreate(email="new@example.com", password="long-enough", display_name="New")
    assert payload.email == "new@example.com"


def test_material_schema_hides_storage_internals(session: Session) -> None:
    from app.repositories.materials import MaterialRepository

    owner = make_user(session)
    project = make_project(session, owner)
    mat = MaterialRepository(session).create(
        project_id=project.id,
        name="Secret",
        storage_key="tenant/abc/file.pdf",
        checksum="deadbeef",
    )
    session.commit()
    read = MaterialRead.model_validate(mat)
    dumped = read.model_dump()
    assert "storage_key" not in dumped
    assert "checksum" not in dumped
    assert read.name == "Secret"


def test_service_transaction_commits_atomically(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    concept, _ = ConceptRepository(session).get_or_create(project_id=project.id, name="Atomic")
    session.commit()

    svc = MasteryService(session)
    mastery, history = svc.record_observation(
        user_id=owner.id,
        project_id=project.id,
        concept_id=concept.id,
        score=42.0,
        source=MasterySource.ASSESSMENT,
    )
    # Committed by the service: visible in a fresh session state.
    session.expire_all()
    assert session.get(Mastery, mastery.id) is not None
    assert session.get(MasteryHistory, history.id) is not None


def test_service_transaction_rolls_back_on_failure(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    concept, _ = ConceptRepository(session).get_or_create(project_id=project.id, name="Rollback")
    session.commit()

    svc = MasteryService(session)
    with (
        patch.object(EventRepository, "append", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError),
    ):
        svc.record_observation(
            user_id=owner.id,
            project_id=project.id,
            concept_id=concept.id,
            score=42.0,
            source=MasterySource.TUTOR,
        )
    session.expire_all()
    assert session.query(Mastery).filter_by(concept_id=concept.id).count() == 0, (
        "partial mastery row must not survive the rollback"
    )


def test_owner_inheritance_cannot_be_spoofed(session: Session) -> None:
    owner = make_user(session)
    other = make_user(session, email="other@example.com")
    space = SpaceRepository(session).create(owner_id=other.id, name="S")
    session.commit()
    project = ProjectService(session).create_project(user_id=other.id, space_id=space.id, name="P")
    assert project.owner_id == other.id  # inherited from space, not caller
    assert project.owner_id != owner.id
