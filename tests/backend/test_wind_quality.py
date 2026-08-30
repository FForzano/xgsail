"""wind_quality: sensor-fault detection over a station's observations, and
its integration in wind_lookup (a faulty station is dropped from both the
fused wind and the live snapshot).

The stuck-vane fixtures are the real readings of a Meteobridge station at
Lido delle Nazioni (IT) captured on 2026-08-30: the anemometer works, the
vane is frozen at 245.0 deg. A station 8 km away reported 32-48 deg at the
same instants with an almost identical wind *speed*, which is what makes it
a sensor fault rather than weather.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from backend.services import wind_lookup, wind_quality

START = datetime(2026, 8, 30, 11, 0, tzinfo=timezone.utc)


def _rows(samples, *, step_minutes=5.0, gust=None):
    """Observation rows from ``(twd_deg, tws_kts)`` pairs, one every
    ``step_minutes``."""
    return [
        SimpleNamespace(observed_at=START + timedelta(minutes=step_minutes * i),
                        twd_deg=twd, tws_kts=tws, gust_kts=gust)
        for i, (twd, tws) in enumerate(samples)
    ]


# Real capture: direction pinned at 245.0 while the anemometer moves.
CAPO_HOORN_SPEEDS_KTS = [4.3, 5.4, 5.2, 5.2, 5.4, 5.6, 5.8, 6.0, 6.4]
STUCK_VANE = _rows([(245.0, kts) for kts in CAPO_HOORN_SPEEDS_KTS])

# The healthy neighbour at the same instants: direction moves too.
HEALTHY = _rows(list(zip([48.0, 47.0, 47.0, 44.0, 44.0, 32.0, 38.0, 37.0, 41.0],
                         CAPO_HOORN_SPEEDS_KTS)))


def test_healthy_station_is_not_faulty():
    assert wind_quality.station_readings_are_faulty(HEALTHY) is None


def test_stuck_vane_is_detected_on_the_real_capture():
    reason = wind_quality.station_readings_are_faulty(STUCK_VANE)
    assert reason is not None
    assert "stuck vane" in reason
    assert "245.0" in reason


def test_no_rows_is_not_a_fault():
    assert wind_quality.station_readings_are_faulty([]) is None


def test_too_few_rows_is_never_a_fault():
    """Thin evidence must not condemn a station: a wrong verdict silently
    discards a healthy one, which is the worse failure."""
    assert wind_quality.station_readings_are_faulty(STUCK_VANE[:2]) is None


def test_too_short_a_span_is_never_a_fault():
    burst = _rows([(245.0, kts) for kts in CAPO_HOORN_SPEEDS_KTS], step_minutes=0.2)
    assert wind_quality.station_readings_are_faulty(burst) is None


def test_steady_direction_with_steady_speed_is_not_a_stuck_vane():
    """A constant direction only condemns the vane when the *other* channel
    is visibly moving — otherwise it is just a steady breeze."""
    steady = _rows([(245.0, 5.0)] * 9)
    assert wind_quality.station_readings_are_faulty(steady) is None


def test_stuck_anemometer_is_detected():
    reason = wind_quality.station_readings_are_faulty(
        _rows(list(zip([10.0, 30.0, 55.0, 40.0, 20.0, 35.0, 60.0, 25.0, 15.0], [7.0] * 9)))
    )
    assert reason is not None
    assert "stuck anemometer" in reason


def test_constant_zero_speed_is_calm_not_a_stuck_anemometer():
    calm = _rows(list(zip([10.0, 30.0, 55.0, 40.0, 20.0, 35.0, 60.0, 25.0, 15.0], [0.0] * 9)))
    assert wind_quality.station_readings_are_faulty(calm) is None


def test_frozen_feed_needs_the_stricter_thresholds():
    """A feed repeating one whole reading fires only for a high-cadence
    station: an hourly METAR/NDBC row repeating a few times is normal
    weather, not a fault."""
    hourly = _rows([(240.0, 8.0)] * 4, step_minutes=60.0, gust=11.0)
    assert wind_quality.station_readings_are_faulty(hourly) is None

    high_cadence = _rows([(240.0, 8.0)] * 13, step_minutes=5.0, gust=11.0)
    reason = wind_quality.station_readings_are_faulty(high_cadence)
    assert reason is not None
    assert "frozen feed" in reason


def test_missing_fields_are_not_read_as_a_repeated_value():
    """A row without a direction is dropped from the check, not counted as
    'the same value again' — otherwise a sparse feed would look frozen."""
    sparse = _rows([(None, kts) for kts in CAPO_HOORN_SPEEDS_KTS])
    assert wind_quality.station_readings_are_faulty(sparse) is None


# --- integration: wind_lookup drops the station -------------------------


class _FakeRepo:
    def __init__(self, stations, observations):
        self._stations = stations
        self._observations = observations

    def find_within(self, lat, lng, *, providers=None, max_km=50, limit=3):
        return list(self._stations)[:limit]

    def list_observations(self, station_id, *, start=None, end=None, limit=500):
        return self._observations.get(station_id, [])

    def list_estimates_for_cells(self, cells, start, end):
        return []


def _station(station_id, name):
    return SimpleNamespace(id=station_id, provider="cumulus_realtime",
                           lat=44.74, lng=12.24, name=name)


def _patched(repo):
    return (
        patch("backend.services.wind_lookup.get_repos",
              return_value=SimpleNamespace(wind=repo)),
        patch("backend.services.wind_lookup.open_meteo.fetch_historical", return_value={}),
        patch("backend.services.wind_lookup.open_meteo.fetch_station", return_value={}),
    )


def test_faulty_station_contributes_no_rows_to_the_bundle():
    repo = _FakeRepo(
        stations=[(_station("broken", "Capo Hoorn"), 1.0),
                  (_station("ok", "Volano"), 8.0)],
        observations={"broken": STUCK_VANE, "ok": HEALTHY},
    )
    p1, p2, p3 = _patched(repo)
    with p1, p2, p3:
        bundle = wind_lookup.gather_raw_wind(44.74, 12.24, START,
                                             START + timedelta(hours=1))

    assert {r["station_id"] for r in bundle["real_stations"]} == {"ok"}


def test_live_snapshot_skips_the_faulty_station_for_the_next_one():
    """The map arrow must not be drawn from a dead vane either — same helper,
    same exclusion."""
    repo = _FakeRepo(
        stations=[(_station("broken", "Capo Hoorn"), 1.0),
                  (_station("ok", "Volano"), 8.0)],
        observations={"broken": STUCK_VANE, "ok": HEALTHY},
    )
    p1, p2, p3 = _patched(repo)
    with p1, p2, p3:
        snapshot = wind_lookup.live_snapshot(44.74, 12.24, at=START + timedelta(minutes=20))

    assert snapshot is not None
    assert snapshot["station_name"] == "Volano"


# --- operator-facing health --------------------------------------------

NOW = START + timedelta(hours=1)


def _codes(issues):
    return {i["code"] for i in issues}


def test_health_is_empty_for_a_working_station():
    station = _station("ok", "Volano")
    assert wind_quality.station_health(station, HEALTHY, now=NOW) == []


def test_health_flags_a_station_without_coordinates():
    """It is silently skipped by find_within's SQL filter, so it never
    reaches the fusion at all — nothing else would ever say so."""
    station = SimpleNamespace(id="x", provider="cumulus_realtime", lat=None, lng=None, name="X")
    assert _codes(wind_quality.station_health(station, HEALTHY, now=NOW)) == {"no_coordinates"}


def test_health_flags_a_station_with_no_recent_data():
    station = _station("quiet", "Quiet")
    assert _codes(wind_quality.station_health(station, [], now=NOW)) == {"no_data"}


def test_health_flags_a_stale_feed():
    station = _station("stale", "Stale")
    old = _rows([(60.0, 5.0), (70.0, 6.0)])
    issues = wind_quality.station_health(station, old, now=START + timedelta(hours=12))
    assert _codes(issues) == {"stale"}


def test_health_reports_the_stuck_vane_with_its_reason():
    station = _station("broken", "Capo Hoorn")
    issues = wind_quality.station_health(station, STUCK_VANE, now=NOW)
    assert _codes(issues) == {"faulty"}
    assert "stuck vane" in issues[0]["detail"]


def test_health_reports_several_problems_at_once():
    station = SimpleNamespace(id="x", provider="cumulus_realtime", lat=None, lng=None, name="X")
    issues = wind_quality.station_health(station, STUCK_VANE, now=NOW)
    assert _codes(issues) == {"no_coordinates", "faulty"}
