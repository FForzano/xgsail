"""The "in arrivo" banner's upcoming-activity query must not leak the
per-race bookkeeping activity that `routers/races.py::_create_race_activity`
auto-creates for every scheduled race.

Uses a real (sqlite, in-memory) SQLAlchemy session against the actual ORM
models/repo — not a hand-rolled fake — because the bug is in a WHERE clause,
and a fake session can't exercise that. Only the tables this repo method
touches are created (not the full schema, which relies on Postgres-only
functions), so this stays a lightweight unit test rather than the DB fixture
the project intentionally avoids in this test suite.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import ActivityORM, UserClubORM, UserGroupORM
from backend.repositories.sql.activity_repo import SqlActivityRepo

CLUB = uuid.uuid4()
USER = uuid.uuid4()


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[ActivityORM.__table__, UserClubORM.__table__, UserGroupORM.__table__]
    )
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        s.add(UserClubORM(user_id=USER, club_id=CLUB, status="active"))
        s.commit()
    return SqlActivityRepo(Session)


def _future():
    return datetime.now(timezone.utc) + timedelta(days=1)


def test_race_bookkeeping_activity_is_excluded(repo):
    """A scheduled race's auto-created activity (type="race") must not
    surface in the personal "in arrivo" banner — it's internal GPS
    bookkeeping for the race, already represented by the regatta itself
    (see `SqlRegattaRepo.list_upcoming_for_user`, which is what the banner
    uses instead)."""
    repo.create({
        "name": "Race 1", "type": "race", "club_id": CLUB,
        "status": "planned", "started_at": _future(),
    })
    assert repo.list_upcoming_for_user(USER) == []


def test_non_race_planned_activity_still_surfaces(repo):
    """The exclusion is specific to type="race" — a genuine club training
    announcement must keep showing up."""
    training = repo.create({
        "name": "Allenamento", "type": "training", "club_id": CLUB,
        "status": "planned", "started_at": _future(),
    })
    result = repo.list_upcoming_for_user(USER)
    assert [a.id for a in result] == [training.id]
