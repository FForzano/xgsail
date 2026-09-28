"""``wind_lookup.live_snapshot`` now fuses every raw source in range the
same way the session-analysis estimate does (``xgsail_windfusion.
fuse_waypoint`` + ``blend_direction``), instead of picking one source
unblended. No database: ``backend.services.wind_lookup.get_repos`` is
patched with a fake repo, in the style of test_wind_multi_station.py."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services import wind_lookup

# A fixed "now" well in the past of any real test-run clock, so the
# archive/forecast branch in gather_raw_wind (`end < datetime.now(utc)`)
# deterministically picks the archive endpoint (fetch_historical) — the
# "now" edge case below is about a station lagging *this* instant, not
# about the real wall clock.
AT = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)


def _station(station_id, provider="noaa_ndbc", lat=45.0, lng=9.0, name="Buoy"):
    return SimpleNamespace(id=station_id, provider=provider, lat=lat, lng=lng, name=name)


def _obs(observed_at, twd_deg=180, tws_kts=10, gust_kts=None):
    return SimpleNamespace(observed_at=observed_at, twd_deg=twd_deg, tws_kts=tws_kts,
                           gust_kts=gust_kts)


def _track_obs(obs_id, observed_at, lat=45.0, lng=9.0, twd_deg=90.0, confidence=0.9, kind="tack"):
    return SimpleNamespace(id=obs_id, observed_at=observed_at, lat=lat, lng=lng,
                           twd_deg=twd_deg, confidence=confidence, kind=kind)


class FakeWindRepo:
    def __init__(self, stations=(), observations=None, track_observations=()):
        self._stations = list(stations)
        self._observations = observations or {}
        self._track_observations = list(track_observations)

    def find_within(self, lat, lng, *, providers=None, max_km=50, limit=3):
        return list(self._stations)[:limit]

    def list_observations(self, station_id, *, start=None, end=None, limit=500):
        return self._observations.get(station_id, [])

    def list_estimates_for_cells(self, cells, start, end):
        return []

    def list_track_observations_near(self, lat, lng, radius_km, start, end, *,
                                     exclude_session_id):
        return list(self._track_observations)


def _fake_repos(wind_repo):
    return SimpleNamespace(wind=wind_repo)


def test_live_snapshot_fuses_station_and_model_not_just_the_nearest():
    station = _station("s1", name="Lido")
    repo = FakeWindRepo(
        stations=[(station, 4.0)],
        observations={"s1": [_obs(AT - timedelta(minutes=20), twd_deg=10.0, tws_kts=12.0)]},
    )
    model_rows = {"icon_d2": [{"observed_at": AT, "twd_deg": 30.0, "tws_kts": 8.0, "gust_kts": None}]}
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)), \
         patch("backend.services.wind_lookup.open_meteo.fetch_historical", return_value=model_rows):
        result = wind_lookup.live_snapshot(45.0, 9.0, at=AT)

    assert result is not None
    assert result["provider"] == "fusion"
    types = {s["type"] for s in result["sources"]}
    assert types == {"real_station", "model_regional"}
    assert all(s["weight_share"] > 0 for s in result["sources"])


def test_live_snapshot_shares_sum_to_about_one():
    station = _station("s1")
    repo = FakeWindRepo(
        stations=[(station, 4.0)],
        observations={"s1": [_obs(AT - timedelta(minutes=20))]},
        track_observations=[_track_obs("t1", AT - timedelta(minutes=5))],
    )
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)), \
         patch("backend.services.wind_lookup.open_meteo.fetch_historical", return_value={}):
        result = wind_lookup.live_snapshot(45.0, 9.0, at=AT)

    assert result is not None
    assert sum(s["weight_share"] for s in result["sources"]) == pytest.approx(1.0, abs=0.02)


def test_live_snapshot_pulls_direction_toward_track_observations():
    station = _station("s1")
    repo = FakeWindRepo(
        stations=[(station, 4.0)],
        observations={"s1": [_obs(AT - timedelta(minutes=5), twd_deg=30.0, tws_kts=10.0)]},
        track_observations=[_track_obs(f"t{i}", AT, twd_deg=0.0, lat=45.0, lng=9.0)
                            for i in range(5)],
    )
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)), \
         patch("backend.services.wind_lookup.open_meteo.fetch_historical", return_value={}):
        result = wind_lookup.live_snapshot(45.0, 9.0, at=AT)

    assert result is not None
    diff = abs((result["twd_deg"] - 30.0 + 180.0) % 360.0 - 180.0)
    assert diff > 5.0  # pulled meaningfully away from the raw fused 30 degrees
    assert any(s["type"] == "gps_tack" for s in result["sources"])


def test_live_snapshot_returns_none_when_nothing_covers_the_point():
    repo = FakeWindRepo(stations=[])
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)), \
         patch("backend.services.wind_lookup.open_meteo.fetch_historical", return_value={}):
        assert wind_lookup.live_snapshot(45.0, 9.0, at=AT) is None


def test_live_snapshot_at_now_still_counts_a_station_reading_20_minutes_old():
    """The "now" edge case: a real station's newest reading is typically a
    few minutes behind ``at``, and a source never extrapolates past its own
    span. ``LIVE_HOLD_LATEST`` must hold the stale reading (weight decayed
    by the gap) rather than drop the station out of every live snapshot."""
    station = _station("s1")
    repo = FakeWindRepo(
        stations=[(station, 4.0)],
        observations={"s1": [_obs(AT - timedelta(minutes=20), twd_deg=200.0, tws_kts=14.0)]},
    )
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)), \
         patch("backend.services.wind_lookup.open_meteo.fetch_historical", return_value={}):
        result = wind_lookup.live_snapshot(45.0, 9.0, at=AT)

    assert result is not None
    assert any(s["type"] == "real_station" for s in result["sources"])
    assert result["latest_observed_at"] == (AT - timedelta(minutes=20)).isoformat()


def test_live_snapshot_response_keys_are_a_superset_of_the_old_schema():
    station = _station("s1", name="Lido")
    repo = FakeWindRepo(
        stations=[(station, 4.0)],
        observations={"s1": [_obs(AT - timedelta(minutes=5))]},
    )
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)), \
         patch("backend.services.wind_lookup.open_meteo.fetch_historical", return_value={}):
        result = wind_lookup.live_snapshot(45.0, 9.0, at=AT)

    assert result is not None
    old_station_keys = {"provider", "station_name", "lat", "lng", "observed_at",
                        "twd_deg", "tws_kts", "gust_kts"}
    old_model_keys = {"provider", "model", "lat", "lng", "observed_at",
                      "twd_deg", "tws_kts", "gust_kts"}
    assert old_station_keys <= result.keys()
    assert old_model_keys <= result.keys()
    assert {"confidence", "latest_observed_at", "sources"} <= result.keys()
