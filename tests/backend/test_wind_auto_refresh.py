"""Neighbour-driven wind re-analysis (``backend/services/wind_auto_refresh.py``,
``track_wind.changed_observations``/``apply_analysis_payload``, and the
``SqlSessionRepo`` bookkeeping behind them).

Database-free, following ``test_track_wind_observations.py``: in-memory SQLite
with the real repositories over the real ORM tables. ``routers/system.py``
cannot be imported here (see ``test_admin_access_log.py``), so its two-line
upsert wiring — ``consume_auto_flag`` then ``apply_analysis_payload(...,
mark_neighbours=not auto)`` — is reproduced by ``_upsert`` below. The worker
dispatch (``ingestion.refresh_wind_cache``) and upload resolution are patched.
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.models import (
    SessionAnalysisORM, SessionLegORM, SessionManeuverORM, SessionORM, SessionUploadORM,
    WindTrackObservationORM,
)
from backend.repositories.sql.session_repo import SqlSessionRepo
from backend.repositories.sql.wind_repo import SqlWindRepo
from backend.services import track_wind, wind_auto_refresh, wind_lookup

LAT, LNG = 45.0, 9.0
START = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
END = datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    # One shared connection: the concurrency test runs the processor on a
    # second thread, and each new connection to :memory: is an empty database.
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[
        SessionORM.__table__, SessionUploadORM.__table__, SessionAnalysisORM.__table__,
        SessionLegORM.__table__, SessionManeuverORM.__table__,
        WindTrackObservationORM.__table__,
    ])
    Session = sessionmaker(bind=engine, future=True)
    return Session


@pytest.fixture
def repos(db, monkeypatch):
    ingest = SimpleNamespace(calls=[])
    ingest.set_reanalysis_status = lambda uid, status, error=None: ingest.calls.append(
        (uid, status))
    fake = SimpleNamespace(sessions=SqlSessionRepo(db), wind=SqlWindRepo(db), ingest=ingest)
    monkeypatch.setenv("WIND_AUTO_REFRESH_ENABLED", "1")
    monkeypatch.setattr(wind_auto_refresh, "AUTO_REFRESH_PAUSE_S", 0)
    monkeypatch.setattr(wind_auto_refresh, "_utcnow", lambda: NOW)
    with patch("backend.services.track_wind.get_repos", return_value=fake), \
         patch("backend.services.wind_auto_refresh.get_repos", return_value=fake):
        yield fake


def _session(db, *, start=START, end=END, lat=LAT, lng=LNG, true_wind_source="fusion",
             unavailable=None, analysed=True, legs=True, **state):
    """A session with (by default) one analysed leg at (lat, lng)."""
    with db() as s:
        orm = SessionORM(activity_id=uuid.uuid4(), boat_id=uuid.uuid4(),
                         started_at=start, ended_at=end, **state)
        s.add(orm)
        s.flush()
        if analysed:
            s.add(SessionAnalysisORM(
                session_id=orm.id, unavailable_reason=unavailable,
                true_wind=[{"t": 0, "twd_deg": 200, "source": true_wind_source}]
                if true_wind_source else None))
        if legs:
            s.add(SessionLegORM(session_id=orm.id, leg_type="upwind", start_time=0,
                                end_time=60, duration_sec=60, distance_nm=0.1,
                                avg_speed_kts=5, max_speed_kts=6, avg_vmg_kts=4,
                                start_lat=lat, start_lon=lng,
                                end_lat=lat + 0.002, end_lon=lng + 0.002))
        s.commit()
        return orm.id


def _obs(observed_at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc), lat=LAT, lng=LNG,
         twd=200.0, kind="tack"):
    return {"observed_at": observed_at.isoformat(), "lat": lat, "lng": lng,
            "twd_deg": twd, "confidence": 0.8, "kind": kind}


def _state(db, sid):
    with db() as s:
        return s.get(SessionORM, sid)


def _aware(dt):
    return None if dt is None else dt.replace(tzinfo=timezone.utc)


def _upsert(sid, payload):
    """``routers/system.py::upsert_session_analysis``'s wind-observation wiring."""
    auto = wind_auto_refresh.consume_auto_flag(sid)
    track_wind.apply_analysis_payload(sid, {"track_wind_observations": payload},
                                      mark_neighbours=not auto)
    return auto


def test_radius_is_three_km_and_shared():
    assert wind_lookup.TRACK_OBS_RADIUS_KM == 3.0
    assert wind_auto_refresh.TRACK_OBS_RADIUS_KM is wind_lookup.TRACK_OBS_RADIUS_KM


# --- what counts as a material change ----------------------------------------

def _parsed(**kw):
    return track_wind._parse_row(_obs(**kw))


def test_identical_sets_do_not_change():
    rows = [_parsed(), _parsed(kind="gybe")]
    assert track_wind.changed_observations(rows, [dict(r) for r in rows]) == []


def test_small_jitter_in_time_and_direction_is_not_a_change():
    t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    old = [_parsed(observed_at=t, twd=359.0)]
    new = [_parsed(observed_at=t + timedelta(seconds=3), twd=1.5)]  # 2.5° across north
    assert track_wind.changed_observations(old, new) == []


def test_direction_moved_beyond_threshold_is_a_change():
    old, new = [_parsed(twd=200.0)], [_parsed(twd=204.0)]
    assert [o["twd_deg"] for o in track_wind.changed_observations(old, new)] == [204.0]


def test_added_removed_and_kind_mismatch_are_changes():
    t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    old = [_parsed(observed_at=t), _parsed(observed_at=t + timedelta(minutes=5))]
    new = [_parsed(observed_at=t, kind="gybe"), _parsed(observed_at=t + timedelta(minutes=9))]
    assert len(track_wind.changed_observations(old, new)) == 4


# --- marking -----------------------------------------------------------------

def test_unchanged_observations_mark_nobody(repos, db):
    source = _session(db)
    neighbour = _session(db, lat=LAT + 0.01)
    track_wind.apply_analysis_payload(source, {"track_wind_observations": [_obs()]})

    _upsert(source, [_obs()])

    assert _state(db, neighbour).wind_stale_at is None


def test_change_marks_only_in_radius_in_time_non_sensor_others(repos, db):
    source = _session(db)
    near = _session(db, lat=LAT + 0.01)                       # ~1.1 km
    no_own_obs_near = _session(db, lat=LAT - 0.02)             # ~2.2 km, has no observations
    edge_of_window = _session(db, start=END + timedelta(minutes=20),
                              end=END + timedelta(hours=1))    # starts 1h20 after obs: out
    within_pad = _session(db, start=datetime(2026, 7, 1, 10, 25, tzinfo=timezone.utc),
                          end=END)                             # 25 min after obs: in
    far = _session(db, lat=LAT + 0.04)                         # ~4.4 km
    later = _session(db, start=START + timedelta(hours=4), end=END + timedelta(hours=4))
    sensor = _session(db, true_wind_source="sensor")
    unavailable = _session(db, unavailable="no_wind_data", true_wind_source=None)
    never_analysed = _session(db, analysed=False)

    _upsert(source, [_obs()])

    stale = {sid for sid in (source, near, no_own_obs_near, edge_of_window, within_pad, far,
                             later, sensor, unavailable, never_analysed)
             if _state(db, sid).wind_stale_at is not None}
    assert stale == {near, no_own_obs_near, within_pad}
    assert _aware(_state(db, near).wind_stale_at) == NOW


def test_a_maneuver_point_alone_locates_a_neighbour(repos, db):
    source = _session(db)
    neighbour = _session(db, legs=False, lat=LAT + 0.01)
    with db() as s:
        s.add(SessionManeuverORM(session_id=neighbour, maneuver_type="tack",
                                 original_maneuver_type="tack", start_time=0, end_time=5,
                                 duration_sec=5, speed_loss_kts=1, speed_before_kts=5,
                                 speed_min_kts=4, speed_after_kts=5, recovery_time_sec=3,
                                 heading_change_deg=90, start_lat=LAT + 0.01, start_lon=LNG))
        s.commit()

    _upsert(source, [_obs()])

    assert _state(db, neighbour).wind_stale_at is not None


def test_removed_observations_mark_too(repos, db):
    source = _session(db)
    neighbour = _session(db, lat=LAT + 0.01)
    track_wind.apply_analysis_payload(source, {"track_wind_observations": [_obs()]})

    _upsert(source, [])

    assert _state(db, neighbour).wind_stale_at is not None


def test_kill_switch_stops_marking(repos, db, monkeypatch):
    monkeypatch.setenv("WIND_AUTO_REFRESH_ENABLED", "0")
    source = _session(db)
    neighbour = _session(db, lat=LAT + 0.01)

    _upsert(source, [_obs()])

    assert _state(db, neighbour).wind_stale_at is None


# --- one generation ------------------------------------------------------------

def test_an_auto_refresh_produced_analysis_marks_nobody(repos, db):
    refreshed = _session(db, wind_stale_at=NOW - timedelta(hours=1),
                         wind_auto_refresh_pending_at=NOW - timedelta(minutes=2))
    neighbour = _session(db, lat=LAT + 0.01)

    assert _upsert(refreshed, [_obs(twd=250.0)]) is True

    assert _state(db, neighbour).wind_stale_at is None
    after = _state(db, refreshed)
    assert after.wind_auto_refresh_pending_at is None
    assert after.wind_stale_at is None  # this refresh answered the mark


def test_the_flag_is_consumed_once(repos, db):
    refreshed = _session(db, wind_auto_refresh_pending_at=NOW - timedelta(minutes=2))
    neighbour = _session(db, lat=LAT + 0.01)
    _upsert(refreshed, [_obs()])

    assert _upsert(refreshed, [_obs(twd=250.0)]) is False  # a later, ordinary analysis

    assert _state(db, neighbour).wind_stale_at is not None


def test_a_mark_that_arrived_during_the_refresh_survives(repos, db):
    refreshed = _session(db, wind_stale_at=NOW - timedelta(minutes=1),
                         wind_auto_refresh_pending_at=NOW - timedelta(minutes=2))

    _upsert(refreshed, [])

    assert _state(db, refreshed).wind_stale_at is not None


def test_an_expired_flag_is_not_taken_for_an_auto_refresh(repos, db):
    sid = _session(db, wind_auto_refresh_pending_at=NOW - timedelta(hours=2))
    neighbour = _session(db, lat=LAT + 0.01)

    assert _upsert(sid, [_obs()]) is False

    assert _state(db, sid).wind_auto_refresh_pending_at is None
    assert _state(db, neighbour).wind_stale_at is not None


# --- the processor -------------------------------------------------------------

def _upload(status=None):
    return SimpleNamespace(id=uuid.uuid4(), reanalysis_status=status)


def _run(uploads=None, refresh=None):
    uploads = uploads or {}
    with patch("backend.services.wind_auto_refresh.nav_source.resolve_nav_upload",
               side_effect=lambda sid: uploads.get(sid, _upload())), \
         patch("backend.services.wind_auto_refresh.ingestion.refresh_wind_cache",
               side_effect=refresh) as dispatched:
        result = wind_auto_refresh.run_pending()
    return result, [c.args[0] for c in dispatched.call_args_list]


def test_debounce_and_cooldown_are_respected(repos, db):
    fresh = _session(db, wind_stale_at=NOW - timedelta(minutes=5))
    cooling = _session(db, wind_stale_at=NOW - timedelta(hours=1),
                       wind_auto_refreshed_at=NOW - timedelta(hours=2))
    due = _session(db, wind_stale_at=NOW - timedelta(minutes=20),
                   wind_auto_refreshed_at=NOW - timedelta(hours=7))

    _, dispatched = _run()

    assert dispatched == [due]
    stamped = _state(db, due)
    assert _aware(stamped.wind_auto_refreshed_at) == NOW
    assert _aware(stamped.wind_auto_refresh_pending_at) == NOW
    assert _state(db, fresh).wind_auto_refreshed_at is None


def test_at_most_max_per_run_oldest_first(repos, db):
    sids = [_session(db, wind_stale_at=NOW - timedelta(hours=10 - i)) for i in range(5)]

    _, dispatched = _run()

    assert dispatched == sids[:wind_auto_refresh.AUTO_REFRESH_MAX_PER_RUN]


def test_refreshes_run_sequentially_and_hold_the_reanalysis_guard(repos, db):
    sids = [_session(db, wind_stale_at=NOW - timedelta(hours=1)) for _ in range(2)]
    uploads = {sid: _upload() for sid in sids}
    in_flight = []

    def refresh(sid):
        assert not in_flight, "two refreshes overlapped"
        in_flight.append(sid)
        assert repos.ingest.calls[-1] == (uploads[sid].id, "running")
        in_flight.pop()

    _run(uploads, refresh)

    assert repos.ingest.calls == [(uploads[sids[0]].id, "running"), (uploads[sids[0]].id, None),
                                  (uploads[sids[1]].id, "running"), (uploads[sids[1]].id, None)]


def test_a_session_with_a_user_reanalysis_running_is_skipped(repos, db):
    busy = _session(db, wind_stale_at=NOW - timedelta(hours=2))
    other = _session(db, wind_stale_at=NOW - timedelta(hours=1))

    _, dispatched = _run({busy: _upload("running")})

    assert dispatched == [other]
    assert _state(db, busy).wind_stale_at is not None
    assert _state(db, busy).wind_auto_refreshed_at is None


def test_a_concurrent_run_is_a_no_op(repos, db):
    _session(db, wind_stale_at=NOW - timedelta(hours=1))
    started, release = threading.Event(), threading.Event()
    results = {}

    def slow_refresh(sid):
        started.set()
        release.wait(5)

    def first():
        results["first"] = _run(refresh=slow_refresh)

    t = threading.Thread(target=first)
    t.start()
    assert started.wait(5)
    try:
        assert wind_auto_refresh.run_pending() == {"skipped": "busy"}
    finally:
        release.set()
        t.join(5)
    assert len(results["first"][1]) == 1


def test_kill_switch_stops_the_processor(repos, db, monkeypatch):
    _session(db, wind_stale_at=NOW - timedelta(hours=1))
    monkeypatch.setenv("WIND_AUTO_REFRESH_ENABLED", "false")

    result, dispatched = _run()

    assert result == {"skipped": "disabled"} and dispatched == []


def test_a_failing_refresh_is_not_retried_every_tick(repos, db, monkeypatch):
    sid = _session(db, wind_stale_at=NOW - timedelta(hours=1))

    def boom(_sid):
        raise RuntimeError("worker down")

    result, dispatched = _run(refresh=boom)
    assert dispatched == [sid] and result["failed"] == [str(sid)]
    assert _state(db, sid).wind_stale_at is not None  # left for a later run

    for minutes in (10, 20, 60 * 5):
        monkeypatch.setattr(wind_auto_refresh, "_utcnow",
                            lambda m=minutes: NOW + timedelta(minutes=m))
        assert _run(refresh=boom)[1] == []

    monkeypatch.setattr(wind_auto_refresh, "_utcnow", lambda: NOW + timedelta(hours=6))
    assert _run(refresh=boom)[1] == [sid]  # after the cooldown, once more


def test_a_permanently_failing_mark_is_eventually_dropped(repos, db, monkeypatch):
    sid = _session(db, wind_stale_at=NOW - timedelta(hours=1))
    monkeypatch.setattr(wind_auto_refresh, "_utcnow", lambda: NOW + timedelta(days=3))

    result, dispatched = _run()

    assert dispatched == [] and result["dropped"] == 1
    assert _state(db, sid).wind_stale_at is None


def test_nothing_to_refresh_from_clears_the_mark(repos, db):
    no_track = _session(db, wind_stale_at=NOW - timedelta(hours=2))
    no_upload = _session(db, wind_stale_at=NOW - timedelta(hours=1))

    def refresh(_sid):
        raise ValueError("No GPS track to sample wind from")

    _run({no_upload: None}, refresh)

    for sid in (no_track, no_upload):
        state = _state(db, sid)
        assert state.wind_stale_at is None and state.wind_auto_refresh_pending_at is None
