"""``SqlActivityRepo.session_totals`` — the per-activity figures the diary
rows print (session count, and distance/duration of a one-session outing).

Database-free, following ``test_session_activity_photos.py``: an in-memory
SQLite engine with the real repository over the real ORM tables.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import (
    ActivityORM,
    BoatORM,
    SessionORM,
    SessionStatsORM,
    SessionUploadORM,
    UserBoatORM,
    UserORM,
    UserRoleORM,
)
from backend.repositories.sql.activity_repo import SqlActivityRepo


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            UserORM.__table__,
            UserRoleORM.__table__,
            BoatORM.__table__,
            UserBoatORM.__table__,
            ActivityORM.__table__,
            SessionORM.__table__,
            SessionUploadORM.__table__,
            SessionStatsORM.__table__,
        ],
    )
    return sessionmaker(bind=engine, future=True)


def _activity(db):
    with db() as s:
        a = ActivityORM(type="solo")
        s.add(a)
        s.commit()
        return a.id


def _session(db, activity_id, *, distance_m=None, duration_s=None, name="Aria"):
    with db() as s:
        b = BoatORM(name=name, sail_number="ITA 1")
        s.add(b)
        s.flush()
        sess = SessionORM(activity_id=activity_id, boat_id=b.id)
        s.add(sess)
        s.flush()
        if distance_m is not None or duration_s is not None:
            s.add(SessionStatsORM(session_id=sess.id, distance_m=distance_m, duration_s=duration_s))
        s.commit()
        return sess.id


def test_single_session_activity_carries_its_distance_and_duration(db):
    activity_id = _activity(db)
    _session(db, activity_id, distance_m=9740.0, duration_s=2880)

    totals = SqlActivityRepo(db).session_totals([activity_id])

    assert totals[activity_id] == {"session_count": 1, "distance_m": 9740.0, "duration_s": 2880}


def test_multi_session_activity_has_a_count_but_no_summed_distance(db):
    # Several boats in one outing: their distances added together are not a
    # distance anyone sailed, so only the count is reported.
    activity_id = _activity(db)
    _session(db, activity_id, distance_m=9000.0, duration_s=2800, name="Aria")
    _session(db, activity_id, distance_m=8000.0, duration_s=2700, name="Brezza")

    totals = SqlActivityRepo(db).session_totals([activity_id])

    assert totals[activity_id] == {"session_count": 2, "distance_m": None, "duration_s": None}


def test_session_without_stats_yet_counts_with_null_figures(db):
    activity_id = _activity(db)
    _session(db, activity_id)

    totals = SqlActivityRepo(db).session_totals([activity_id])

    assert totals[activity_id] == {"session_count": 1, "distance_m": None, "duration_s": None}


def test_activity_with_no_sessions_is_absent_and_empty_input_is_cheap(db):
    activity_id = _activity(db)
    repo = SqlActivityRepo(db)

    assert repo.session_totals([activity_id]) == {}
    assert repo.session_totals([]) == {}
