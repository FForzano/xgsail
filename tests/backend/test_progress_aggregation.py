"""Personal sailing-progression summary (``backend.services.progress.user_progress``).

Real sqlite session against the actual ORM/repo, same reasoning as the
neighbouring tests: the behaviour under test is SQL (crew scoping) plus
calendar arithmetic (local-time month/day bucketing), and a hand-rolled fake
session could not exercise either.

``user_progress`` resolves its repositories via ``get_repos()`` at call time,
so each test monkeypatches ``backend.services.progress.get_repos`` to return a
tiny stand-in exposing ``.sessions`` (a real ``SqlSessionRepo`` on the
in-memory sqlite engine) and ``.boats`` (a minimal stub with ``.get``).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.services.progress as progress_module
from backend.db.base import Base
from backend.db.models import (
    ActivityORM,
    SessionCrewORM,
    SessionORM,
    SessionStatsORM,
    UserBoatORM,
)
from backend.repositories.sql.session_repo import SqlSessionRepo

ME = uuid.uuid4()
OTHER = uuid.uuid4()
BOAT = uuid.uuid4()


class _FakeBoat:
    def __init__(self, name):
        self.name = name


class _FakeBoatRepo:
    """Minimal stand-in for repos.boats — only `.get` is used by progress.py."""

    def __init__(self, names: "dict[uuid.UUID, str]" = None):
        self._names = names or {}

    def get(self, boat_id):
        name = self._names.get(boat_id)
        return _FakeBoat(name) if name is not None else None


class _FakeRepos:
    def __init__(self, Session, boat_names=None):
        self.sessions = SqlSessionRepo(Session)
        self.boats = _FakeBoatRepo(boat_names)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        ActivityORM.__table__,
        SessionORM.__table__,
        SessionCrewORM.__table__,
        SessionStatsORM.__table__,
        UserBoatORM.__table__,
    ])
    Session = sessionmaker(bind=engine, future=True)
    return Session


def _activity(Session) -> uuid.UUID:
    with Session() as s:
        activity = ActivityORM(type="solo", visibility="private", created_by=ME)
        s.add(activity)
        s.commit()
        return activity.id


def _session(Session, *, boat_id=BOAT, started_at=None, crew=(),
             distance_m=None, duration_s=None, max_speed_kts=None,
             avg_polar_pct=None) -> uuid.UUID:
    activity_id = _activity(Session)
    with Session() as s:
        sess = SessionORM(activity_id=activity_id, boat_id=boat_id, started_at=started_at)
        s.add(sess)
        s.commit()
        session_id = sess.id
        for user_id in crew:
            s.add(SessionCrewORM(session_id=session_id, user_id=user_id, sailing_role="crew"))
        if any(v is not None for v in (distance_m, duration_s, max_speed_kts, avg_polar_pct)):
            s.add(SessionStatsORM(
                session_id=session_id, distance_m=distance_m, duration_s=duration_s,
                max_speed_kts=max_speed_kts, avg_polar_pct=avg_polar_pct,
            ))
        s.commit()
    return session_id


def _patch_repos(monkeypatch, Session, boat_names=None):
    monkeypatch.setattr(progress_module, "get_repos", lambda: _FakeRepos(Session, boat_names))


def test_crew_scoping_not_boat_membership(db, monkeypatch):
    """A session crewed only by OTHER must not credit ME, even when ME is
    linked to the same boat via `user_boats` — using boat membership instead
    of `session_crew` would leak a co-owner's miles into my own totals."""
    Session = db
    with Session() as s:
        s.add(UserBoatORM(user_id=ME, boat_id=BOAT, role="owner"))
        s.commit()
    when = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    _session(Session, started_at=when, crew=[OTHER], distance_m=10000, duration_s=3600)
    _patch_repos(monkeypatch, Session)

    result = progress_module.user_progress(ME, year=2026)

    assert result.totals.sessions == 0
    assert result.totals.distance_m == 0.0


def test_local_time_month_bucketing_crosses_year_boundary(db, monkeypatch):
    """A session at 2025-12-31T22:30:00Z with a +120 minute local offset is
    2026-01-01T00:30 locally — it must land in January 2026's `by_month[0]`,
    not in December 2025."""
    Session = db
    when = datetime(2025, 12, 31, 22, 30, tzinfo=timezone.utc)
    _session(Session, started_at=when, crew=[ME])
    _patch_repos(monkeypatch, Session)

    result_2026 = progress_module.user_progress(ME, year=2026, tz_offset_minutes=120)
    assert result_2026.by_month[0] == 1
    assert sum(result_2026.by_month) == 1
    assert result_2026.totals.sessions == 1

    result_2025 = progress_module.user_progress(ME, year=2025, tz_offset_minutes=120)
    assert result_2025.by_month[11] == 0
    assert result_2025.totals.sessions == 0


def test_started_at_null_is_excluded(db, monkeypatch):
    """A session with no `started_at` (never got a track) must not count
    anywhere, even though it has a crew row."""
    Session = db
    _session(Session, started_at=None, crew=[ME])
    _patch_repos(monkeypatch, Session)

    result = progress_module.user_progress(ME, year=2026)

    assert result.totals.sessions == 0
    assert result.totals.days == 0
    assert sum(result.by_month) == 0


def test_missing_session_stats_still_counts_session_but_not_distance(db, monkeypatch):
    """A crewed session whose analysis hasn't run yet (no `session_stats`
    row) still counts as a session/day, but contributes zero distance and
    duration — a failed/pending analysis must not erase the outing."""
    Session = db
    when = datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc)
    _session(Session, started_at=when, crew=[ME])
    _patch_repos(monkeypatch, Session)

    result = progress_module.user_progress(ME, year=2026)

    assert result.totals.sessions == 1
    assert result.totals.days == 1
    assert result.totals.distance_m == 0.0
    assert result.totals.duration_s == 0
    assert result.by_month[4] == 1


def test_days_is_distinct_local_calendar_dates(db, monkeypatch):
    """Two sessions on the same local day count as 2 sessions but 1 day."""
    Session = db
    _session(Session, started_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc), crew=[ME])
    _session(Session, started_at=datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc), crew=[ME])
    _patch_repos(monkeypatch, Session)

    result = progress_module.user_progress(ME, year=2026)

    assert result.totals.sessions == 2
    assert result.totals.days == 1


def test_personal_bests_are_all_time_not_year_scoped(db, monkeypatch):
    """A max-speed record set in 2024 must still show up when the caller is
    viewing 2026 — personal bests are all-time, unlike `totals`/`by_month`."""
    Session = db
    when = datetime(2024, 7, 4, 12, 0, tzinfo=timezone.utc)
    session_id = _session(Session, started_at=when, crew=[ME], max_speed_kts=28.5)
    _patch_repos(monkeypatch, Session, boat_names={BOAT: "Laser 123"})

    result = progress_module.user_progress(ME, year=2026)

    speed_bests = [b for b in result.personal_bests if b.metric == "max_speed_kts"]
    assert len(speed_bests) == 1
    best = speed_bests[0]
    assert best.value == 28.5
    assert best.session_id == session_id
    assert best.boat_id == BOAT
    assert best.boat_name == "Laser 123"
    # The session route is nested under its activity, so dropping activity_id
    # from the projection would silently turn every record row into a dead link.
    with Session() as s:
        assert best.activity_id == s.get(SessionORM, session_id).activity_id


def test_personal_best_duration_serializes_as_float(db, monkeypatch):
    """`ProgressBestModel.value` is typed `float` for every metric, so a
    duration_s best must serialise as e.g. 3600.0, not the int 3600."""
    Session = db
    when = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    _session(Session, started_at=when, crew=[ME], duration_s=3600)
    _patch_repos(monkeypatch, Session)

    result = progress_module.user_progress(ME, year=2026)

    duration_bests = [b for b in result.personal_bests if b.metric == "duration_s"]
    assert len(duration_bests) == 1
    assert duration_bests[0].value == 3600.0
    assert isinstance(duration_bests[0].value, float)


def test_available_years_lists_distinct_local_years_ascending(db, monkeypatch):
    """`available_years` must list every distinct local year the user has
    sailed, sorted ascending, regardless of which year is being queried."""
    Session = db
    _session(Session, started_at=datetime(2023, 6, 1, 12, 0, tzinfo=timezone.utc), crew=[ME])
    _session(Session, started_at=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc), crew=[ME])
    _session(Session, started_at=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc), crew=[ME])
    _patch_repos(monkeypatch, Session)

    result = progress_module.user_progress(ME, year=2025)

    assert result.available_years == [2023, 2024, 2025]


def test_previous_year_and_previous_by_month_are_year_minus_one(db, monkeypatch):
    """`previous`/`previous_by_month` must reflect `year - 1`, not the
    current year's own data and not some other adjacent year."""
    Session = db
    _session(Session, started_at=datetime(2025, 3, 15, 12, 0, tzinfo=timezone.utc),
             crew=[ME], distance_m=5000, duration_s=1800)
    _session(Session, started_at=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
             crew=[ME], distance_m=9000, duration_s=2700)
    _patch_repos(monkeypatch, Session)

    result = progress_module.user_progress(ME, year=2026)

    assert result.previous.sessions == 1
    assert result.previous.distance_m == 5000.0
    assert result.previous_by_month[2] == 1
    assert sum(result.previous_by_month) == 1

    assert result.totals.sessions == 1
    assert result.totals.distance_m == 9000.0
    assert result.by_month[7] == 1


def test_by_month_always_has_twelve_entries(db, monkeypatch):
    """`by_month`/`previous_by_month` are fixed-length 12-element lists even
    with zero sessions, since the frontend indexes them positionally."""
    Session = db
    _patch_repos(monkeypatch, Session)

    result = progress_module.user_progress(ME, year=2026)

    assert len(result.by_month) == 12
    assert len(result.previous_by_month) == 12
