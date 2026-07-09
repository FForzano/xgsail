"""Session analysis runner.

Loads raw sensor data and runs the full processing pipeline,
saving results alongside the processed data.
"""

import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _to_timestamp(t) -> float:
    """Convert ISO string or datetime to Unix timestamp."""
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, str):
        t = t.replace("Z", "+00:00")
        return datetime.fromisoformat(t).timestamp()
    if isinstance(t, datetime):
        return t.timestamp()
    return 0.0

from processing import track
from processing.maneuvers import detect_maneuvers, maneuver_summary
from processing.models import GpsPoint, ImuReading, SessionMetadata, WindReading
from processing.polar import generate_polar, polar_to_chart_data
from processing.stats import (
    correlation_matrix,
    leg_performance_ranking,
    session_statistics,
    violin_plot_data,
)
from processing.straight_lines import _haversine_nm, leg_comparison, segment_legs
from processing.vmg import compute_vmg_series
from processing.wind_estimation import estimate as estimate_wind
from processing.wind_estimation import refinements_from


def load_sensor_json(path: Path) -> list[dict]:
    """Load sensor JSON file."""
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data if isinstance(data, list) else data.get("data", [])


def parse_gps(records: list[dict]) -> "tuple[list[GpsPoint], list[dict], list[dict]]":
    """Runs the joint position/motion estimator (see ``processing/track.py``)
    and merges the result into the ``GpsPoint`` shape the rest of the
    pipeline consumes. Returns ``(points, position, motion)`` — the two raw
    series are needed by the caller to persist them as their own artifacts
    (see ``analyze_session``)."""
    position, motion = track.estimate(records)
    return track.merge(position, motion), position, motion


def parse_imu(records: list[dict]) -> list[ImuReading]:
    return [ImuReading(
        timestamp=_to_timestamp(r.get("timestamp", r.get("t", ""))),
        heading_deg=r.get("heading_deg", r.get("heading", 0)),
        pitch_deg=r.get("pitch_deg", r.get("pitch", 0)),
        heel_deg=r.get("heel_deg", r.get("heel", 0)),
        accel_x=r.get("accel_x", 0),
        accel_y=r.get("accel_y", 0),
        accel_z=r.get("accel_z", 0),
    ) for r in records if "timestamp" in r or "t" in r]


def parse_wind(records: list[dict]) -> list[WindReading]:
    return [WindReading(
        timestamp=_to_timestamp(r.get("timestamp", r.get("t", ""))),
        apparent_speed_kts=r.get("apparent_speed_kts", r.get("aws_kn", r.get("speed_kts", 0))),
        apparent_angle_deg=r.get("apparent_angle_deg", r.get("awa", r.get("angle_deg", 0))),
    ) for r in records if "timestamp" in r or "t" in r]


def analyze_session(data_dir: Path) -> dict:
    """Run full analysis pipeline on a session directory.

    Expects directory structure:
        data_dir/
            gps.json
            imu.json
            wind.json
            pressure.json
            manifest.json
    """
    gps, estimated_position, estimated_motion = parse_gps(load_sensor_json(data_dir / "gps.json"))
    imu = parse_imu(load_sensor_json(data_dir / "imu.json"))
    wind = parse_wind(load_sensor_json(data_dir / "wind.json"))

    if not gps:
        return {"error": "No GPS data found"}

    # True wind calculation is a pluggable seam — see
    # ``processing/wind_estimation.py`` for the strategy (today: onboard
    # sensor > cached regional wind > rough GPS-tack estimate). wind_cache.json
    # is the backend's raw multi-source bundle (real stations, every
    # Open-Meteo candidate model, existing grid estimates) — see
    # ``backend/services/wind_lookup.gather_raw_wind``, not a single
    # pre-picked series.
    raw_wind_bundle = load_sensor_json(data_dir / "wind_cache.json")
    true_wind = estimate_wind(gps, wind, imu, raw_wind_bundle)
    # Only non-empty when true_wind came from a real onboard sensor — fed
    # back to the backend's wind_estimates grid (see routers/system.py::
    # _apply_wind_refinements). Never derived from cache/GPS-estimate.
    wind_refinements = refinements_from(gps, true_wind)

    avg_twd = None
    if true_wind:
        avg_twd = float(np.mean([tw["twd_deg"] for tw in true_wind]))

    # Maneuver detection
    maneuvers = detect_maneuvers(gps, imu, avg_twd)
    m_summary = maneuver_summary(maneuvers)

    # Leg segmentation
    legs = segment_legs(gps, maneuvers, true_wind, imu)
    l_comparison = leg_comparison(legs)

    # Polar diagram — average (actual performance) and max-per-bucket
    # ("target") curves, so the UI can plot both together.
    polar_points = generate_polar(gps, true_wind)
    polar_chart = polar_to_chart_data(polar_points)
    polar_target_points = generate_polar(gps, true_wind, use_max=True)

    # VMG series
    vmg_series = compute_vmg_series(gps, true_wind)

    # Statistics
    sess_stats = session_statistics(gps, wind, imu)
    violin = violin_plot_data(maneuvers)
    correlations = correlation_matrix(gps, true_wind, imu)
    leg_ranking = leg_performance_ranking(legs)

    # Scalar aggregates for the DB session_stats table (distance/duration/speed).
    summary = _session_summary(gps)

    # Build result
    result = {
        "summary": summary,
        "maneuvers": [asdict(m) for m in maneuvers],
        "maneuver_summary": m_summary,
        "legs": [asdict(l) for l in legs],
        "leg_comparison": l_comparison,
        # Chart-shaped polar for the blob artifact; flat points for the DB
        # (polar_points table, keyed by session).
        "polar": polar_chart,
        "polar_points": [{
            "twa_deg": p.twa_deg, "tws_kts": p.tws_kts,
            "speed_kts": p.boat_speed_kts, "vmg_kts": p.vmg_kts,
            "sample_count": p.sample_count,
        } for p in polar_points],
        "polar_target": [{
            "twa_deg": p.twa_deg, "tws_kts": p.tws_kts,
            "speed_kts": p.boat_speed_kts, "vmg_kts": p.vmg_kts,
            "sample_count": p.sample_count,
        } for p in polar_target_points],
        "vmg_series": [asdict(v) for v in vmg_series],
        "true_wind": true_wind,
        "session_stats": sess_stats,
        "violin": violin,
        "correlations": correlations,
        "leg_ranking": leg_ranking,
        # Persisted separately as their own blob artifacts by the caller
        # (handler.py::process_analyze_prefix) — not written directly here
        # since analyze_session stays a pure function (dict in, dict out).
        # The caller pops these back out before posting the rest of `result`
        # to the backend, so they're stored once, not duplicated into
        # analysis.json too.
        "estimated_position": estimated_position,
        "estimated_motion": estimated_motion,
        "wind_refinements": wind_refinements,
    }

    return result


def _session_summary(gps: list[GpsPoint]) -> dict:
    """Scalar session aggregates for the DB ``session_stats`` table.

    ``avg_polar_pct``/``max_polar_pct`` are intentionally omitted — they need a
    reference polar for the boat, not available here (see plan follow-up)."""
    if not gps:
        return {}
    speeds = [p.speed_kts for p in gps]
    distance_m = sum(
        _haversine_nm(gps[i - 1].lat, gps[i - 1].lon, gps[i].lat, gps[i].lon) * 1852.0
        for i in range(1, len(gps))
    )
    return {
        "distance_m": round(distance_m, 1),
        "duration_s": int(_to_timestamp(gps[-1].timestamp) - _to_timestamp(gps[0].timestamp)),
        "avg_speed_kts": round(float(np.mean(speeds)), 2),
        "max_speed_kts": round(float(max(speeds)), 2),
    }


def main():
    """CLI entry point: analyze a session directory."""
    if len(sys.argv) < 2:
        print("Usage: python analyzer.py <session_data_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    if not data_dir.exists():
        print(f"Directory not found: {data_dir}")
        sys.exit(1)

    result = analyze_session(data_dir)

    output_path = data_dir / "analysis.json"
    output_path.write_text(json.dumps(result, indent=2))
    print(f"Analysis written to {output_path}")


if __name__ == "__main__":
    main()
