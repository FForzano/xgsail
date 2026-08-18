"""Whether an upload joined an outing that was already there
(``backend/services/ingestion.py::resolve_session``).

The merge is decided server-side by boat and time window, and until this
existed there was no moment at which the person uploading learned it had
happened. ``resolve_session`` reports it so ``/imports/{id}/complete`` can
say "this was joined to X's outing" and offer to separate it again.

Database-free, following ``test_ingestion_crew.py``.
"""

import types
import uuid
from datetime import datetime, timedelta

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
def repos(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        ActivityORM.__table__,
        BoatORM.__table__,
        SessionORM.__table__,
        SessionUploadORM.__table__,
        UserBoatORM.__table__,
        SessionCrewORM.__table__,
    ])
    Session = sessionmaker(bind=engine, future=True)
    repo = types.SimpleNamespace(
        activities=SqlActivityRepo(Session),
        boats=SqlBoatRepo(Session),
        sessions=SqlSessionRepo(Session),
    )
    monkeypatch.setattr(ingestion, "get_repos", lambda: repo)
    return repo, Session


@pytest.fixture
def boat_id(repos):
    _, Session = repos
    with Session() as s:
        boat = BoatORM(name="Test Boat")
        s.add(boat)
        s.commit()
        return boat.id


def _dt(hours=0):
    # Naive, for the SQLite tzinfo reason documented in test_ingestion_crew.py.
    return datetime(2026, 1, 1) + timedelta(hours=hours)


def test_a_brand_new_session_is_not_reported_as_merged(repos, boat_id):
    resolution = ingestion.resolve_session(
        boat_id=boat_id, started_at=_dt(), ended_at=_dt(1), created_by=uuid.uuid4())

    assert resolution.merged is False


def test_joining_an_existing_window_is_reported_as_merged(repos, boat_id):
    """The bow's phone lands on the helm's session, which nobody asked for."""
    helm, bow = uuid.uuid4(), uuid.uuid4()
    first = ingestion.resolve_session(
        boat_id=boat_id, started_at=_dt(), ended_at=_dt(1), created_by=helm)

    second = ingestion.resolve_session(
        boat_id=boat_id, started_at=_dt(0.5), ended_at=_dt(1.5), created_by=bow)

    assert second.merged is True
    assert second.session.id == first.session.id


def test_a_separate_outing_is_not_reported_as_merged(repos, boat_id):
    ingestion.resolve_session(boat_id=boat_id, started_at=_dt(), ended_at=_dt(1),
                              created_by=uuid.uuid4())

    later = ingestion.resolve_session(boat_id=boat_id, started_at=_dt(6),
                                      ended_at=_dt(7), created_by=uuid.uuid4())

    assert later.merged is False


def test_an_explicitly_chosen_activity_is_never_reported_as_merged(repos, boat_id):
    """One session per boat per activity is the documented rule: joining the
    session of an activity you picked yourself is not a surprise, and a
    "separate this?" prompt there would be noise."""
    repo, _ = repos
    activity = repo.activities.create({"type": "training", "visibility": "club"})
    ingestion.resolve_session(boat_id=boat_id, started_at=_dt(), ended_at=_dt(1),
                              activity_id=activity.id, created_by=uuid.uuid4())

    second = ingestion.resolve_session(
        boat_id=boat_id, started_at=_dt(0.5), ended_at=_dt(1.5),
        activity_id=activity.id, created_by=uuid.uuid4())

    assert second.merged is False


def test_find_or_create_session_still_returns_the_session(repos, boat_id):
    """The three other ingestion entry points keep their existing signature."""
    session = ingestion.find_or_create_session(
        boat_id=boat_id, started_at=_dt(), created_by=uuid.uuid4())

    assert session.boat_id == boat_id
