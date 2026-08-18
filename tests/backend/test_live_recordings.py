"""Presence rows for in-progress recordings
(``backend/repositories/sql/live_recording_repo.py``).

The behaviours that matter are all in the repository: liveness is a read-time
predicate over ``last_seen_at`` with no cleanup job behind it, and start and
heartbeat are the same idempotent write. Router-level membership scoping is
not covered here — this suite has no ``TestClient`` — so the boat-membership
gate in ``routers/live_recordings.py`` is verified by hand.

Database-free, following ``test_ingestion_crew.py``.
"""

import types
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import BoatORM, LiveRecordingORM, UserBoatORM
from backend.db.models.live_recording import LIVE_STALE_AFTER
from backend.repositories.sql.live_recording_repo import SqlLiveRecordingRepo

NOW = datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        BoatORM.__table__,
        UserBoatORM.__table__,  # BoatORM.members is lazy="selectin"
        LiveRecordingORM.__table__,
    ])
    Session = sessionmaker(bind=engine, future=True)
    return SqlLiveRecordingRepo(Session), Session


@pytest.fixture
def boats(repo):
    _, Session = repo
    with Session() as s:
        a, b = BoatORM(name="Aria"), BoatORM(name="Brezza")
        s.add_all([a, b])
        s.commit()
        return a.id, b.id


def test_a_fresh_heartbeat_is_live_and_a_stale_one_is_not(repo, boats):
    live, _ = repo
    aria, _brezza = boats
    fresh, gone = uuid.uuid4(), uuid.uuid4()
    live.upsert(boat_id=aria, user_id=fresh, now=NOW - timedelta(minutes=5))
    # An app killed mid-outing simply stops heartbeating; nothing has to
    # notice, and there is no job that prunes it.
    live.upsert(boat_id=aria, user_id=gone, now=NOW - LIVE_STALE_AFTER - timedelta(minutes=1))

    active = live.list_active([aria], now=NOW)

    assert [r.user_id for r in active] == [fresh]


def test_heartbeat_keeps_the_original_start_time(repo, boats):
    """The banner shows how long the outing has been running — a heartbeat
    must not reset it every few minutes."""
    live, _ = repo
    aria, _ = boats
    user, recording = uuid.uuid4(), "recording-1"
    live.upsert(boat_id=aria, user_id=user, client_recording_id=recording,
                now=NOW - timedelta(minutes=40))

    row = live.upsert(boat_id=aria, user_id=user, client_recording_id=recording, now=NOW)

    assert row.started_at == NOW - timedelta(minutes=40)
    assert row.last_seen_at == NOW


def test_a_different_recording_resets_the_start_time(repo, boats):
    live, _ = repo
    aria, _ = boats
    user = uuid.uuid4()
    live.upsert(boat_id=aria, user_id=user, client_recording_id="recording-1",
                now=NOW - timedelta(minutes=40))

    row = live.upsert(boat_id=aria, user_id=user, client_recording_id="recording-2", now=NOW)

    assert row.started_at == NOW


def test_upsert_never_duplicates_a_person_on_a_boat(repo, boats):
    """The app retries the announce whenever connectivity returns, without
    tracking whether the first attempt got through."""
    live, Session = repo
    aria, _ = boats
    user = uuid.uuid4()
    for _ in range(3):
        live.upsert(boat_id=aria, user_id=user, client_recording_id="recording-1", now=NOW)

    with Session() as s:
        assert s.query(LiveRecordingORM).count() == 1


def test_end_is_idempotent(repo, boats):
    live, _ = repo
    aria, _ = boats
    user = uuid.uuid4()
    live.upsert(boat_id=aria, user_id=user, now=NOW)

    assert live.end(boat_id=aria, user_id=user) is True
    assert live.end(boat_id=aria, user_id=user) is False  # already gone, no error
    assert live.list_active([aria], now=NOW) == []


def test_listing_is_scoped_to_the_boats_asked_for(repo, boats):
    live, _ = repo
    aria, brezza = boats
    live.upsert(boat_id=aria, user_id=uuid.uuid4(), now=NOW)
    live.upsert(boat_id=brezza, user_id=uuid.uuid4(), now=NOW)

    assert [r.boat_id for r in live.list_active([aria], now=NOW)] == [aria]
    assert live.list_active([], now=NOW) == []


def test_your_own_recording_is_excluded(repo, boats):
    """You do not need telling that you are recording — the banner answers
    "is anybody *else* aboard recording this outing"."""
    live, _ = repo
    aria, _ = boats
    me, them = uuid.uuid4(), uuid.uuid4()
    live.upsert(boat_id=aria, user_id=me, now=NOW)
    live.upsert(boat_id=aria, user_id=them, now=NOW)

    active = live.list_active([aria], now=NOW, exclude_user_id=me)

    assert [r.user_id for r in active] == [them]


def test_prune_drops_only_rows_nothing_will_refresh(repo, boats):
    live, Session = repo
    aria, _ = boats
    live.upsert(boat_id=aria, user_id=uuid.uuid4(), now=NOW - timedelta(hours=48))
    live.upsert(boat_id=aria, user_id=uuid.uuid4(), now=NOW)

    assert live.prune(now=NOW) == 1
    with Session() as s:
        assert s.query(LiveRecordingORM).count() == 1
