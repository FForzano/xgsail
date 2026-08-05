"""Regression tests for auto-seeding the recording user as session crew
(``backend/services/ingestion.py``'s ``add_recorder_as_crew`` and its wiring
into ``find_or_create_session``).

Follows the precedent in ``test_boat_session_notes.py``/``test_boat_notebook.py``:
database-free, in-memory SQLite, only the tables actually touched or needed
for SQLAlchemy metadata resolution. ``find_or_create_session`` reaches its
repos via the module-level ``get_repos()``, so it's monkeypatched to return a
fake ``Repositories``-shaped object backed by the SQLite session factory.
"""

import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import (
    ActivityORM,
    BoatORM,
    SessionCrewORM,
    SessionORM,
    SessionUploadORM,
    UserBoatORM,
)
from backend.repositories.sql.activity_repo import SqlActivityRepo
from backend.repositories.sql.boat_repo import SqlBoatRepo
from backend.repositories.sql.session_repo import SqlSessionRepo
from backend.services import ingestion


@pytest.fixture
def repos():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            ActivityORM.__table__,
            BoatORM.__table__,
            SessionORM.__table__,
            SessionUploadORM.__table__,  # sessions.primary_nav_upload_id FK target (use_alter=True)
            UserBoatORM.__table__,  # BoatORM.members is lazy="selectin"; also queried directly by get_member
            SessionCrewORM.__table__,
        ],
    )
    Session = sessionmaker(bind=engine, future=True)
    return types.SimpleNamespace(
        activities=SqlActivityRepo(Session),
        boats=SqlBoatRepo(Session),
        sessions=SqlSessionRepo(Session),
    ), Session


@pytest.fixture
def boat_id(repos):
    _, Session = repos
    with Session() as s:
        boat = BoatORM(name="Test Boat")
        s.add(boat)
        s.commit()
        return boat.id


def _dt(offset_hours=0):
    # Naive on purpose: SQLite drops tzinfo on a DateTime(timezone=True)
    # round trip, and find_for_boat_window compares freshly-built Python
    # datetimes against ones read back from the DB — aware vs. naive would
    # raise on SQLite even though real (always-aware) Postgres never hits
    # this. Timezone handling isn't what this file tests.
    return datetime(2026, 1, 1) + timedelta(hours=offset_hours)


def _crew_roles(Session, session_id):
    with Session() as s:
        rows = s.query(SessionCrewORM).filter(SessionCrewORM.session_id == session_id).all()
        return {r.user_id: r.sailing_role for r in rows}


# --- add_recorder_as_crew (direct) ------------------------------------------

def test_uses_boat_default_role_when_set(repos, boat_id):
    repo, Session = repos
    user_id = uuid.uuid4()
    repo.boats.add_member(boat_id, user_id=user_id, role="visitor", default_sailing_role="skipper")
    session_id = uuid.uuid4()
    with Session() as s:
        s.add(SessionORM(id=session_id, activity_id=uuid.uuid4(), boat_id=boat_id))
        s.commit()

    ingestion.add_recorder_as_crew(repo, boat_id, session_id, user_id)

    assert _crew_roles(Session, session_id) == {user_id: "skipper"}


def test_falls_back_to_crew_when_member_has_no_default_role(repos, boat_id):
    repo, Session = repos
    user_id = uuid.uuid4()
    repo.boats.add_member(boat_id, user_id=user_id, role="visitor")  # no default_sailing_role
    session_id = uuid.uuid4()
    with Session() as s:
        s.add(SessionORM(id=session_id, activity_id=uuid.uuid4(), boat_id=boat_id))
        s.commit()

    ingestion.add_recorder_as_crew(repo, boat_id, session_id, user_id)

    assert _crew_roles(Session, session_id) == {user_id: "crew"}


def test_falls_back_to_crew_when_not_a_boat_member(repos, boat_id):
    """Recording a session doesn't require being a registered boat member —
    a visiting sailor's own device still puts them in the crew list."""
    repo, Session = repos
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    with Session() as s:
        s.add(SessionORM(id=session_id, activity_id=uuid.uuid4(), boat_id=boat_id))
        s.commit()

    ingestion.add_recorder_as_crew(repo, boat_id, session_id, user_id)

    assert _crew_roles(Session, session_id) == {user_id: "crew"}


def test_idempotent_on_repeat_call(repos, boat_id):
    repo, Session = repos
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    with Session() as s:
        s.add(SessionORM(id=session_id, activity_id=uuid.uuid4(), boat_id=boat_id))
        s.commit()

    ingestion.add_recorder_as_crew(repo, boat_id, session_id, user_id)
    ingestion.add_recorder_as_crew(repo, boat_id, session_id, user_id)  # must not raise

    assert _crew_roles(Session, session_id) == {user_id: "crew"}


# --- find_or_create_session wiring ------------------------------------------

def test_new_session_seeds_created_by_as_crew(repos, boat_id, monkeypatch):
    repo, Session = repos
    monkeypatch.setattr(ingestion, "get_repos", lambda: repo)
    user_id = uuid.uuid4()

    session = ingestion.find_or_create_session(
        boat_id=boat_id, started_at=_dt(), created_by=user_id
    )

    assert _crew_roles(Session, session.id) == {user_id: "crew"}


def test_created_by_none_seeds_no_crew(repos, boat_id, monkeypatch):
    """The dominant device-upload case (a boat/club-owned tracker) has no
    known user at all — nothing should be fabricated."""
    repo, Session = repos
    monkeypatch.setattr(ingestion, "get_repos", lambda: repo)

    session = ingestion.find_or_create_session(boat_id=boat_id, started_at=_dt(), created_by=None)

    assert _crew_roles(Session, session.id) == {}


def test_reused_session_adds_second_recorder_too(repos, boat_id, monkeypatch):
    """Two devices merging into the same boat/time window (the merge-gap
    reuse branch) means two people were genuinely aboard — both end up as
    crew of the one resulting session, not just whoever created it first."""
    repo, Session = repos
    monkeypatch.setattr(ingestion, "get_repos", lambda: repo)
    first_user, second_user = uuid.uuid4(), uuid.uuid4()

    first = ingestion.find_or_create_session(
        boat_id=boat_id, started_at=_dt(), ended_at=_dt(1), created_by=first_user
    )
    second = ingestion.find_or_create_session(
        boat_id=boat_id, started_at=_dt(0.5), ended_at=_dt(1.5), created_by=second_user
    )

    assert first.id == second.id  # same merge-gap window, one shared session
    assert _crew_roles(Session, first.id) == {first_user: "crew", second_user: "crew"}
