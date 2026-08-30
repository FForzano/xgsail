"""Worker-side wind estimation: the weighted_fusion strategy (blend vs the
legacy pick-first), tier precedence, and the grid-refinement contract."""

import pytest

from processing.models import GpsPoint, WindReading
from processing.wind_estimation import (
    _flatten_bundle,
    _fuse_bundle,
    refinements_from,
    weighted_fusion,
)


def _bundle_multi_source():
    """One waypoint whose station, two models, and grid all cover t=1000."""
    return [{
        "lat": 45.0, "lng": 9.0,
        "real_stations": [
            {"station_lat": 45.1, "station_lng": 9.1, "distance_km": 12.0,
             "observed_at": 1000, "twd_deg": 10, "tws_kts": 12, "gust_kts": 15},
            {"station_lat": 45.1, "station_lng": 9.1, "distance_km": 12.0,
             "observed_at": 4600, "twd_deg": 20, "tws_kts": 14, "gust_kts": None},
        ],
        "model_candidates": {
            "icon_d2": [{"observed_at": 1000, "twd_deg": 30, "tws_kts": 10},
                        {"observed_at": 4600, "twd_deg": 40, "tws_kts": 11}],
            "gfs_seamless": [{"observed_at": 1000, "twd_deg": 350, "tws_kts": 9},
                             {"observed_at": 4600, "twd_deg": 0, "tws_kts": 9}],
        },
        "grid_estimates": [{"time_bucket": 1000, "twd_deg": 15, "tws_kts": 13, "confidence": 0.8}],
    }]


def test_fuse_bundle_blends_instead_of_picking_one():
    fused = _fuse_bundle(_bundle_multi_source())
    at_1000 = [r for r in fused if r["observed_at"] == 1000.0]
    assert len(at_1000) == 1
    twd = at_1000[0]["twd_deg"]
    # Sources at t=1000 are 10/30/350/15 deg — the vector mean must land near
    # North (not 180), pulled toward the higher-prior station + grid.
    assert twd > 340 or twd < 40
    # And the fused speed sits within the sources' spread (9..13 kt).
    assert 9.0 <= at_1000[0]["tws_kts"] <= 13.0


def test_fuse_bundle_wraps_direction_correctly():
    # 350 and 10 with comparable weight must never average to ~180.
    bundle = [{
        "lat": 0.0, "lng": 0.0,
        "real_stations": [{"distance_km": 1.0, "observed_at": 100, "twd_deg": 350, "tws_kts": 10}],
        "model_candidates": {"icon_d2": [{"observed_at": 100, "twd_deg": 10, "tws_kts": 10}]},
        "grid_estimates": [],
    }]
    fused = _fuse_bundle(bundle)
    twd = fused[0]["twd_deg"]
    assert twd > 340 or twd < 20


def test_fuse_bundle_keeps_single_source_times():
    # A time only one source covers still produces a row (no data dropped).
    bundle = [{
        "lat": 0.0, "lng": 0.0, "real_stations": [],
        "model_candidates": {"icon_d2": [
            {"observed_at": 100, "twd_deg": 90, "tws_kts": 5},
            {"observed_at": 200, "twd_deg": 90, "tws_kts": 5},
        ]},
        "grid_estimates": [],
    }]
    fused = _fuse_bundle(bundle)
    assert {r["observed_at"] for r in fused} == {100.0, 200.0}
    assert all(r["twd_deg"] == pytest.approx(90.0) for r in fused)


def test_weighted_fusion_uses_bundle_when_no_sensor():
    gps = [GpsPoint(timestamp=2000.0, lat=45.0, lon=9.0, speed_kts=5, heading_deg=100),
           GpsPoint(timestamp=3000.0, lat=45.0, lon=9.0, speed_kts=5, heading_deg=100)]
    series = weighted_fusion(gps, [], None, _bundle_multi_source())
    assert series, "expected a fused series"
    assert all(r["source"] == "fusion" for r in series)
    assert len(series) == len(gps)


def test_weighted_fusion_sensor_takes_precedence_over_bundle():
    # GPS spanning the wind reading so apparent->true resolves.
    gps = [GpsPoint(timestamp=1500.0, lat=45.0, lon=9.0, speed_kts=6, heading_deg=90),
           GpsPoint(timestamp=2500.0, lat=45.0, lon=9.0, speed_kts=6, heading_deg=90)]
    wind = [WindReading(timestamp=2000.0, apparent_speed_kts=12, apparent_angle_deg=40)]
    series = weighted_fusion(gps, wind, None, _bundle_multi_source())
    assert series
    assert all(r["source"] == "sensor" for r in series)


def test_weighted_fusion_empty_everything_returns_empty():
    gps = [GpsPoint(timestamp=float(i), lat=45.0, lon=9.0, speed_kts=0, heading_deg=0)
           for i in range(5)]  # too short for a GPS tack estimate
    assert weighted_fusion(gps, [], None, []) == []


def test_refinements_only_from_real_sensor():
    gps = [GpsPoint(timestamp=10.0, lat=45.0, lon=9.0, speed_kts=5, heading_deg=100)]
    fusion_tw = [{"timestamp": 10.0, "twd_deg": 200, "tws_kts": 11, "source": "fusion"}]
    assert refinements_from(gps, fusion_tw) == []  # blended -> never refines the grid

    sensor_tw = [{"timestamp": 10.0, "twd_deg": 210, "tws_kts": 12, "gust_kts": 15, "source": "sensor"}]
    out = refinements_from(gps, sensor_tw)
    assert len(out) == 1


def test_refinements_contract_matches_backend_reader():
    # Regression pin: the keys _apply_wind_refinements (backend routers/
    # system.py) reads must all be present in what the worker emits.
    gps = [GpsPoint(timestamp=10.0, lat=45.0, lon=9.0, speed_kts=5, heading_deg=100)]
    sensor_tw = [{"timestamp": 10.0, "twd_deg": 210, "tws_kts": 12, "gust_kts": 15, "source": "sensor"}]
    row = refinements_from(gps, sensor_tw)[0]
    for key in ("lat", "lng", "observed_at", "twd_deg", "tws_kts", "gust_kts", "source"):
        assert key in row, f"missing {key}"
    assert row["lng"] == 9.0            # GpsPoint.lon -> emitted as lng
    assert row["gust_kts"] == 15        # now emitted (was silently dropped before)
    assert row["source"] == "onboard_sensor"


def test_legacy_flatten_still_picks_single_source():
    # The old strategy remains available and unchanged (station wins).
    flat = _flatten_bundle(_bundle_multi_source())
    assert len(flat) == 2  # only the station's two rows, models/grid ignored
    assert all(r["tws_kts"] in (12, 14) for r in flat)


def _bundle_two_stations():
    """One waypoint covered by two real stations at very different
    distances, both reporting at t=1000 with clearly separated directions
    so a nearer-station pull is unambiguous."""
    return [{
        "lat": 45.0, "lng": 9.0,
        "real_stations": [
            {"station_id": "near", "station_lat": 45.01, "station_lng": 9.0,
             "distance_km": 2.0, "observed_at": 1000, "twd_deg": 10, "tws_kts": 10},
            {"station_id": "far", "station_lat": 46.0, "station_lng": 10.0,
             "distance_km": 45.0, "observed_at": 1000, "twd_deg": 200, "tws_kts": 10},
        ],
        "model_candidates": {},
        "grid_estimates": [],
    }]


def test_fuse_bundle_pulls_toward_the_nearer_station():
    fused = _fuse_bundle(_bundle_two_stations())
    assert len(fused) == 1
    twd = fused[0]["twd_deg"]
    # 10 and 200 deg are near-opposite; the nearer station (2km, twd=10)
    # must outweigh the farther one (45km, twd=200) so the fused direction
    # lands close to 10, not anywhere near the midpoint (~105) or the far
    # station's own reading.
    assert twd < 60 or twd > 320


def test_legacy_cache_regression_no_station_id_groups_as_a_single_station():
    """Bundles written before multi-station support carry no station_id, only
    the station_lat/station_lng shared by every row of what was always
    exactly one station. Grouping must fall back to those coordinates and
    yield the same single group an explicit station_id would -- this is the
    compatibility contract for wind_cache.json files already on disk."""
    legacy_bundle = _bundle_multi_source()  # fixture above: no station_id anywhere
    tagged_bundle = _bundle_multi_source()
    for row in tagged_bundle[0]["real_stations"]:
        row["station_id"] = "station-a"

    assert _fuse_bundle(legacy_bundle) == _fuse_bundle(tagged_bundle)
    # One fused row per timestamp -- not one group (and one distance) per row.
    assert len(_fuse_bundle(legacy_bundle)) == 2


def test_flatten_bundle_with_two_stations_returns_only_nearest():
    flat = _flatten_bundle(_bundle_two_stations())
    assert len(flat) == 1
    assert flat[0]["twd_deg"] == 10
    assert flat[0]["tws_kts"] == 10
