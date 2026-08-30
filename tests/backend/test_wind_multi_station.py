"""wind_lookup: multi-station support — up to MAX_REAL_STATIONS real
stations per waypoint instead of only the nearest, with per-station
distance/observations and offline-nearest-station fallback for
live_snapshot. No database: backend.services.wind_lookup.get_repos is
patched with a fake repo exposing find_within/list_observations, in the
style of test_wind_cache_merge.py."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services import wind_lookup

START = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
END = datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc)


def _station(station_id, provider="noaa_ndbc", lat=45.1, lng=9.1, name="Station"):
    return SimpleNamespace(id=station_id, provider=provider, lat=lat, lng=lng, name=name)


def _obs(observed_at, twd_deg=180, tws_kts=10, gust_kts=None):
    return SimpleNamespace(observed_at=observed_at, twd_deg=twd_deg, tws_kts=tws_kts,
                           gust_kts=gust_kts)


class FakeWindRepo:
    """Stands in for SqlWindRepo.find_within/list_observations. ``stations``
    is a list of (station, distance_km) pairs returned verbatim by
    find_within (already sorted/limited, as the real repo would do);
    ``observations`` maps station_id -> list of observation rows."""

    def __init__(self, stations, observations):
        self._stations = stations
        self._observations = observations
        self.find_within_calls = []

    def find_within(self, lat, lng, *, providers=None, max_km=50, limit=3):
        self.find_within_calls.append({
            "lat": lat, "lng": lng, "providers": providers, "max_km": max_km, "limit": limit,
        })
        return list(self._stations)[:limit]

    def list_observations(self, station_id, *, start=None, end=None, limit=500):
        return self._observations.get(station_id, [])

    def list_estimates_for_cells(self, cells, start, end):
        return []


def _fake_repos(wind_repo):
    return SimpleNamespace(wind=wind_repo)


def _neutralize_non_station_sources():
    """Patch open_meteo + grid estimates so gather_raw_wind is deterministic
    and offline; tests only care about real_stations behaviour."""
    return (
        patch("backend.services.wind_lookup.open_meteo.fetch_historical", return_value={}),
        patch("backend.services.wind_lookup.open_meteo.fetch_station", return_value={}),
    )


def test_gather_raw_wind_emits_rows_from_several_stations():
    s1, s2 = _station("s1", lat=45.01, lng=9.0), _station("s2", lat=45.5, lng=9.5)
    repo = FakeWindRepo(
        stations=[(s1, 1.5), (s2, 30.0)],
        observations={
            "s1": [_obs(START + timedelta(minutes=10), twd_deg=100, tws_kts=8)],
            "s2": [_obs(START + timedelta(minutes=20), twd_deg=200, tws_kts=15)],
        },
    )
    p1, p2 = _neutralize_non_station_sources()
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)), p1, p2:
        bundle = wind_lookup.gather_raw_wind(45.0, 9.0, START, END)

    rows = bundle["real_stations"]
    assert len(rows) == 2
    by_station = {r["station_id"]: r for r in rows}
    assert by_station["s1"]["distance_km"] == pytest.approx(1.5)
    assert by_station["s2"]["distance_km"] == pytest.approx(30.0)
    assert by_station["s1"]["twd_deg"] == 100
    assert by_station["s2"]["twd_deg"] == 200


def test_station_with_no_observations_contributes_no_rows():
    s1, s2 = _station("s1"), _station("s2")
    repo = FakeWindRepo(
        stations=[(s1, 2.0), (s2, 10.0)],
        observations={
            # s1 (nearest) has nothing cached for the window; only s2 does.
            "s2": [_obs(START + timedelta(minutes=5), twd_deg=220, tws_kts=11)],
        },
    )
    p1, p2 = _neutralize_non_station_sources()
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)), p1, p2:
        bundle = wind_lookup.gather_raw_wind(45.0, 9.0, START, END)

    rows = bundle["real_stations"]
    assert len(rows) == 1
    assert rows[0]["station_id"] == "s2"


def test_live_snapshot_falls_back_to_second_station_when_nearest_is_offline():
    s1 = _station("s1", provider="noaa_ndbc", name="Nearest Buoy")
    s2 = _station("s2", provider="noaa_metar", name="Second Station")
    repo = FakeWindRepo(
        stations=[(s1, 2.0), (s2, 20.0)],
        observations={
            # s1 (nearest) offline: nothing in the window at all.
            "s2": [_obs(datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc), twd_deg=250, tws_kts=14)],
        },
    )
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)):
        result = wind_lookup.live_snapshot(45.0, 9.0, at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc))

    assert result is not None
    assert result["provider"] == "noaa_metar"
    assert result["station_name"] == "Second Station"


def test_live_snapshot_falls_through_to_open_meteo_only_when_no_station_has_data():
    repo = FakeWindRepo(stations=[(_station("s1"), 5.0)], observations={})
    at = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    model_rows = {"icon_d2": [{"observed_at": at, "twd_deg": 300, "tws_kts": 9, "gust_kts": None}]}
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)), \
         patch("backend.services.wind_lookup.open_meteo.fetch_historical", return_value=model_rows):
        result = wind_lookup.live_snapshot(45.0, 9.0, at=at)

    assert result is not None
    assert result["provider"] == "open_meteo"
    assert result["model"] == "icon_d2"


def test_gather_raw_wind_passes_max_real_stations_as_find_within_limit():
    repo = FakeWindRepo(stations=[], observations={})
    p1, p2 = _neutralize_non_station_sources()
    with patch("backend.services.wind_lookup.get_repos", return_value=_fake_repos(repo)), p1, p2:
        wind_lookup.gather_raw_wind(45.0, 9.0, START, END)

    assert len(repo.find_within_calls) == 1
    assert repo.find_within_calls[0]["limit"] == wind_lookup.MAX_REAL_STATIONS
    assert wind_lookup.MAX_REAL_STATIONS == 3
