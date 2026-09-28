"""No onboard sensor and no station/model source → no wind-dependent analysis.

Regression: the old last-resort ``gps_estimate`` tier produced a direction with
``tws_kts``/``twa_deg`` None, and ``segment_legs`` crashed on ``np.mean`` over
those Nones. The product decision is to not analyse against a guessed wind at
all, but still report what needs no wind (distance, speeds)."""

import json
import math
import sys
from types import SimpleNamespace

import pytest

# handler.py builds a real S3 client at import time; stub boto3 for the import
# only (same reason as test_watch_parsing.py) — the test swaps ``handler.s3``.
_boto3 = sys.modules.get("boto3")
sys.modules["boto3"] = SimpleNamespace(client=lambda *a, **k: None)
import handler  # noqa: E402

if _boto3 is not None:
    sys.modules["boto3"] = _boto3
else:
    del sys.modules["boto3"]

from analyzer import analyze_session, load_session_context  # noqa: E402
from processing.models import GpsPoint  # noqa: E402
from processing.wind_estimation import sensor_then_cache, weighted_fusion  # noqa: E402

T0 = 1_800_000_000.0

# Every key backend/routers/system.py::upsert_session_analysis reads, plus the
# observations track_wind.apply_analysis_payload replaces wholesale.
BACKEND_KEYS = (
    "summary", "polar_points", "maneuvers", "legs", "correlations", "violin",
    "maneuver_summary", "leg_comparison", "session_stats", "vmg_series",
    "polar_target", "true_wind", "wind_refinements", "track_wind_observations",
)


def _beat(n_legs=8, leg_s=90, half=45.0, speed=5.0):
    """A 1 Hz beat tacking on a North wind — exactly the track the removed
    GPS-only tier used to turn into a speedless wind estimate (it needed speed
    to vary: it read the slower half of the points as the upwind ones)."""
    gps, t, lat, lon = [], T0, 44.8, 12.3
    for leg in range(n_legs):
        h = half if leg % 2 == 0 else 360.0 - half
        for i in range(leg_s):
            gps.append(GpsPoint(t, lat, lon, speed + 0.2 * (i % 5 - 2), h))
            lat += speed * 1852 / 3600 * math.cos(math.radians(h)) / 111_320
            lon += speed * 1852 / 3600 * math.sin(math.radians(h)) / (111_320 * math.cos(math.radians(lat)))
            t += 1
    return gps


def _write(tmp_path, gps, bundle):
    (tmp_path / "gps.json").write_text(json.dumps([
        {"timestamp": p.timestamp, "lat": p.lat, "lon": p.lon,
         "speed_kts": p.speed_kts, "heading_deg": p.heading_deg} for p in gps]))
    (tmp_path / "wind_cache.json").write_text(json.dumps(bundle))


@pytest.mark.parametrize("strategy", [weighted_fusion, sensor_then_cache])
def test_strategies_return_nothing_without_a_source(strategy):
    assert strategy(_beat(), [], None, []) == []
    empty_waypoint = [{"lat": 44.8, "lng": 12.3, "real_stations": [],
                       "model_candidates": {}, "grid_estimates": [], "track_observations": []}]
    assert strategy(_beat(), [], None, empty_waypoint) == []


@pytest.mark.parametrize("bundle", [[], [{"lat": 44.8, "lng": 12.3, "real_stations": [],
                                         "model_candidates": {"icon_d2": []},
                                         "grid_estimates": [], "track_observations": []}]])
def test_gps_only_session_reports_unavailable_instead_of_crashing(tmp_path, bundle):
    _write(tmp_path, _beat(), bundle)
    result = analyze_session(tmp_path)

    assert result["analysis_unavailable"] == "no_wind_data"
    assert result["summary"]["distance_m"] > 0
    assert result["summary"]["avg_speed_kts"] == pytest.approx(5.0, abs=0.5)
    assert "speed" in result["session_stats"]
    for key in BACKEND_KEYS:
        assert key in result, key
    for key in ("maneuvers", "legs", "polar_points", "polar_target", "vmg_series",
                "true_wind", "wind_refinements", "track_wind_observations"):
        assert result[key] == [], key
    for key in ("maneuver_summary", "leg_comparison", "polar", "violin", "correlations",
                "leg_ranking"):
        assert result[key] is None, key
    # Position/motion estimates need no wind and are still produced.
    assert result["estimated_position"]
    json.dumps(result)


def test_a_normal_result_carries_the_key_as_none(tmp_path):
    rows = [{"observed_at": 0, "twd_deg": 0.0, "tws_kts": 10}, {"observed_at": 2e9, "twd_deg": 0.0, "tws_kts": 10}]
    _write(tmp_path, _beat(), [{"lat": 44.8, "lng": 12.3, "real_stations": [], "grid_estimates": [],
                                "model_candidates": {"icon_d2": rows}}])
    result = analyze_session(tmp_path)
    assert result["analysis_unavailable"] is None
    assert result["legs"] and result["true_wind"]


def test_no_wind_context_skips_maneuvers(tmp_path):
    _write(tmp_path, _beat(), [])
    ctx = load_session_context(tmp_path)
    assert ctx.true_wind == [] and ctx.avg_twd is None
    assert ctx.maneuvers == [] and ctx.track_wind_observations == []


def test_manual_maneuver_without_wind_is_a_clear_error(tmp_path, monkeypatch):
    _write(tmp_path, _beat(), [])
    files = {name: (tmp_path / name).read_bytes() for name in ("gps.json", "wind_cache.json")}

    def get_object(Bucket, Key):
        name = Key.rsplit("/", 1)[-1]
        if name not in files:
            raise KeyError(Key)
        return {"Body": SimpleNamespace(read=lambda: files[name])}

    posted = []
    monkeypatch.setattr(handler, "s3", SimpleNamespace(get_object=get_object))
    monkeypatch.setattr(handler, "_post_system", lambda *a, **k: posted.append(a))
    spec = {"maneuver_id": "m1", "maneuver_type": "tack",
            "start_time": T0 + 85, "end_time": T0 + 95}
    with pytest.raises(ValueError, match="No wind data"):
        handler.process_compute_maneuver("bucket", "processed/uploads/u/", spec)
    assert posted == []
