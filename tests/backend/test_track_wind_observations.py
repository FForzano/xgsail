"""Maneuver-derived wind observations shared between nearby sessions
(``backend/services/track_wind.py``, ``SqlWindRepo.replace_track_observations``
/ ``list_track_observations_near``, ``wind_lookup.gather_raw_wind``).

Database-free, following ``test_live_recordings.py``: an in-memory SQLite
engine and the real repository over the real ORM table. ``routers/system.py``
cannot be imported here (see ``test_admin_access_log.py``), which is why the
absent-key/present-key decision lives in ``track_wind.apply_analysis_payload``
and is tested there. ``ON DELETE CASCADE`` is a Postgres behaviour and is left
to the migration gate.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import WindTrackObservationORM
from backend.repositories.sql.wind_repo import SqlWindRepo
from backend.services import track_wind, wind_lookup

START = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
END = datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc)
LAT, LNG = 45.0, 9.0


@pytest.fixture
def wind():
    engine = create_engine("sqlite:///:memory:")
    # sessions is not created: SQLite does not enforce the FK by default.
    Base.metadata.create_all(engine, tables=[WindTrackObservationORM.__table__])
    return SqlWindRepo(sessionmaker(bind=engine, future=True))


@pytest.fixture
def repos(wind):
    fake = SimpleNamespace(wind=wind)
    with patch("backend.services.track_wind.get_repos", return_value=fake):
        yield fake


def _raw(observed_at="2026-07-01T10:00:00Z", lat=LAT, lng=LNG, twd=200.0,
         confidence=0.8, kind="tack"):
    return {"observed_at": observed_at, "lat": lat, "lng": lng, "twd_deg": twd,
            "confidence": confidence, "kind": kind}


def _near(wind, *, exclude=None, start=START, end=END, lat=LAT, lng=LNG):
    return wind.list_track_observations_near(lat, lng, 5.0, start, end,
                                             exclude_session_id=exclude)


# --- replace, never accumulate ---------------------------------------------

def test_reprocessing_replaces_instead_of_accumulating(repos, wind):
    sid = uuid.uuid4()
    payload = {"track_wind_observations": [_raw(), _raw(kind="gybe")]}

    track_wind.apply_analysis_payload(sid, payload)
    track_wind.apply_analysis_payload(sid, payload)

    assert len(_near(wind)) == 2


def test_empty_list_clears_the_sessions_rows(repos, wind):
    sid = uuid.uuid4()
    track_wind.apply_analysis_payload(sid, {"track_wind_observations": [_raw()]})

    assert track_wind.apply_analysis_payload(sid, {"track_wind_observations": []}) == 0
    assert _near(wind) == []


def test_absent_key_leaves_stored_rows_untouched(repos, wind):
    """An older worker image does not send the key at all."""
    sid = uuid.uuid4()
    track_wind.apply_analysis_payload(sid, {"track_wind_observations": [_raw()]})

    assert track_wind.apply_analysis_payload(sid, {"summary": {}}) is None
    assert len(_near(wind)) == 1


def test_replacing_one_session_leaves_other_sessions_alone(repos, wind):
    a, b = uuid.uuid4(), uuid.uuid4()
    track_wind.apply_analysis_payload(a, {"track_wind_observations": [_raw()]})
    track_wind.apply_analysis_payload(b, {"track_wind_observations": [_raw(twd=10)]})

    track_wind.apply_analysis_payload(a, {"track_wind_observations": []})

    assert [o.twd_deg for o in _near(wind)] == [10]


def test_a_failure_never_raises_into_the_analysis_upsert(repos):
    with patch.object(repos.wind, "replace_track_observations",
                      side_effect=RuntimeError("db down")):
        assert track_wind.apply_analysis_payload(
            uuid.uuid4(), {"track_wind_observations": [_raw()]}) is None


def test_a_non_list_value_is_ignored_without_touching_rows(repos, wind):
    sid = uuid.uuid4()
    track_wind.apply_analysis_payload(sid, {"track_wind_observations": [_raw()]})

    assert track_wind.apply_analysis_payload(sid, {"track_wind_observations": None}) is None
    assert len(_near(wind)) == 1


# --- payload parsing ---------------------------------------------------------

def test_iso_timestamps_parse_to_aware_utc(repos, wind):
    sid = uuid.uuid4()
    track_wind.apply_analysis_payload(sid, {"track_wind_observations": [
        _raw(observed_at="2026-07-01T10:00:00Z"),
        _raw(observed_at="2026-07-01T12:30:00+02:00"),
    ]})

    got = sorted(o.observed_at.replace(tzinfo=timezone.utc) for o in _near(wind))
    assert got == [datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
                   datetime(2026, 7, 1, 10, 30, tzinfo=timezone.utc)]


def test_malformed_rows_are_dropped_and_the_rest_stored(repos, wind):
    stored = track_wind.apply_analysis_payload(uuid.uuid4(), {"track_wind_observations": [
        _raw(),
        _raw(observed_at="not a date"),
        _raw(kind="reach"),
        _raw(confidence=0),
        _raw(confidence=1.5),
        _raw(twd=float("nan")),
        {"lat": LAT},
        "garbage",
    ]})

    assert stored == 1
    assert len(_near(wind)) == 1


def test_direction_is_normalised_into_0_360(repos, wind):
    track_wind.apply_analysis_payload(uuid.uuid4(),
                                      {"track_wind_observations": [_raw(twd=370.0)]})
    assert _near(wind)[0].twd_deg == pytest.approx(10.0)


# --- neighbour lookup --------------------------------------------------------

def test_own_session_is_excluded(wind):
    own, other = uuid.uuid4(), uuid.uuid4()
    rows = [track_wind._parse_row(_raw())]
    wind.replace_track_observations(own, rows)
    wind.replace_track_observations(other, rows)

    got = _near(wind, exclude=own)

    assert len(got) == 1 and got[0].session_id == other


def test_radius_is_exact_not_just_the_bounding_box(wind):
    # ~4.4 km north: inside. ~6.7 km north: outside. A point in the box's
    # corner (4.5 km north and 4.5 km east, ~6.4 km away) is outside too.
    inside = track_wind._parse_row(_raw(lat=LAT + 0.04))
    outside = track_wind._parse_row(_raw(lat=LAT + 0.06))
    corner = track_wind._parse_row(_raw(lat=LAT + 0.0405, lng=LNG + 0.0573))
    wind.replace_track_observations(uuid.uuid4(), [inside, outside, corner])

    assert [o.lat for o in _near(wind)] == [pytest.approx(LAT + 0.04)]


def test_time_window_is_respected(wind):
    rows = [track_wind._parse_row(_raw(observed_at=t)) for t in (
        "2026-07-01T08:59:00Z",   # before
        "2026-07-01T10:00:00Z",   # inside
        "2026-07-01T11:01:00Z",   # after
    )]
    wind.replace_track_observations(uuid.uuid4(), rows)

    got = _near(wind)

    assert len(got) == 1
    assert got[0].observed_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 7, 1, 10, 0, tzinfo=timezone.utc)


# --- the bundle handed to the worker -----------------------------------------

def _gather(wind, session_id):
    fake = SimpleNamespace(wind=SimpleNamespace(
        find_within=lambda *a, **k: [],
        list_estimates_for_cells=lambda *a, **k: [],
        list_track_observations_near=wind.list_track_observations_near,
    ))
    with patch("backend.services.wind_lookup.get_repos", return_value=fake), \
         patch("backend.services.wind_lookup.open_meteo.fetch_historical", return_value={}), \
         patch("backend.services.wind_lookup.open_meteo.fetch_station", return_value={}):
        return wind_lookup.gather_raw_wind(LAT, LNG, START, END, session_id=session_id)


def test_bundle_carries_neighbours_rows_without_identifiers(wind):
    own, other = uuid.uuid4(), uuid.uuid4()
    wind.replace_track_observations(own, [track_wind._parse_row(_raw(twd=90))])
    wind.replace_track_observations(other, [track_wind._parse_row(_raw(twd=200))])

    rows = _gather(wind, own)["track_observations"]

    assert len(rows) == 1
    row = rows[0]
    assert set(row) == {"id", "observed_at", "lat", "lng", "twd_deg", "confidence", "kind"}
    assert uuid.UUID(row["id"])
    assert str(other) not in {str(v) for v in row.values()}
    assert row["twd_deg"] == 200 and row["kind"] == "tack"
    assert datetime.fromisoformat(row["observed_at"]).replace(tzinfo=None) == datetime(
        2026, 7, 1, 10, 0)


def test_bundle_window_is_padded_by_half_an_hour(wind):
    rows = [track_wind._parse_row(_raw(observed_at=t)) for t in (
        "2026-07-01T08:15:00Z",   # 45 min before START: out
        "2026-07-01T08:40:00Z",   # 20 min before START: in
        "2026-07-01T11:20:00Z",   # 20 min after END: in
        "2026-07-01T11:45:00Z",   # 45 min after END: out
    )]
    wind.replace_track_observations(uuid.uuid4(), rows)

    got = _gather(wind, uuid.uuid4())["track_observations"]

    assert [r["observed_at"][11:16] for r in got] == ["08:40", "11:20"]


def test_bundle_always_has_the_key(wind):
    assert _gather(wind, uuid.uuid4())["track_observations"] == []
    assert wind_lookup.TRACK_OBS_RADIUS_KM == 3.0
    assert wind_lookup.TRACK_OBS_TIME_PAD == timedelta(minutes=30)
