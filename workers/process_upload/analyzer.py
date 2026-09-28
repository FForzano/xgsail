"""Session analysis runner.

Loads raw sensor data and runs the full processing pipeline,
saving results alongside the processed data.
"""

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

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

from processing import tack_wind, track
from processing.angles import circular_mean
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


def _slice_by_time(records: list, trim_start: Optional[float], trim_end: Optional[float]) -> list:
    """Filter a list of ``GpsPoint``/``ImuReading``/``WindReading`` instances
    (attribute ``.timestamp``) OR plain ``{"timestamp": ...}`` dicts (the
    ``estimated_position``/``estimated_motion`` shape from ``track.py``) down
    to ``[trim_start, trim_end]`` (either bound ``None`` = open on that side).
    A no-op when both are ``None`` — the common case, no trim set — so an
    untrimmed session's analysis is unchanged."""
    if trim_start is None and trim_end is None:
        return records

    def _ts(r):
        return r.timestamp if hasattr(r, "timestamp") else r["timestamp"]

    return [r for r in records
            if (trim_start is None or _ts(r) >= trim_start)
            and (trim_end is None or _ts(r) <= trim_end)]


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


@dataclass
class SessionContext:
    """Parsed sensor data + resolved true wind for one processed-upload
    prefix — the setup step every entry point into the maneuver pipeline
    needs, whether that's a full session analysis (``analyze_session``) or a
    single manual maneuver's on-demand stat computation
    (``workers/process_upload/handler.py::process_compute_maneuver``).

    ``true_wind``/``avg_twd`` are already refined by the tack/gybe
    observations, which is why the detected ``maneuvers`` live here too: the
    refinement needs them, and a manual maneuver must be measured against the
    same wind the full analysis used."""
    gps: list
    imu: list
    wind: list
    true_wind: list
    avg_twd: Optional[float]
    estimated_position: list
    estimated_motion: list
    wind_refinements: list
    maneuvers: list
    track_wind_observations: list


def load_session_context(
    data_dir: Path, trim_start: Optional[float] = None, trim_end: Optional[float] = None,
) -> Optional[SessionContext]:
    """Parse ``gps.json``/``imu.json``/``wind.json``/``wind_cache.json`` from
    a processed-upload prefix and resolve true wind. Returns ``None`` when
    there's no GPS data — the caller decides how to report that
    (``analyze_session`` returns an ``{"error": ...}`` dict; the manual
    maneuver path raises).

    ``trim_start``/``trim_end`` (unix-epoch seconds — a session's reversible
    track-trim bounds, see ``backend/routers/sessions.py::set_session_trim``)
    slice every parsed series to that window via ``_slice_by_time`` BEFORE
    wind estimation, so the true-wind estimate only considers the kept
    portion too. Raw ``gps.json`` itself is never modified — this only
    affects what one analysis run considers. Both ``None`` (no trim) is a
    no-op, so an untrimmed session's analysis is unchanged."""
    gps, estimated_position, estimated_motion = parse_gps(load_sensor_json(data_dir / "gps.json"))
    imu = parse_imu(load_sensor_json(data_dir / "imu.json"))
    wind = parse_wind(load_sensor_json(data_dir / "wind.json"))

    gps = _slice_by_time(gps, trim_start, trim_end)
    imu = _slice_by_time(imu, trim_start, trim_end)
    wind = _slice_by_time(wind, trim_start, trim_end)
    estimated_position = _slice_by_time(estimated_position, trim_start, trim_end)
    estimated_motion = _slice_by_time(estimated_motion, trim_start, trim_end)

    if not gps:
        return None

    # True wind calculation is a pluggable seam — see
    # ``processing/wind_estimation.py`` for the strategy (today: onboard
    # sensor > fused stations/models/grid, else nothing). wind_cache.json
    # is the backend's raw multi-source bundle (real stations, every
    # Open-Meteo candidate model, existing grid estimates) — see
    # ``backend/services/wind_lookup.gather_raw_wind``, not a single
    # pre-picked series.
    raw_wind_bundle = load_sensor_json(data_dir / "wind_cache.json")
    true_wind = estimate_wind(gps, wind, imu, raw_wind_bundle)
    # Only non-empty when true_wind came from a real onboard sensor — fed
    # back to the backend's wind_estimates grid (see routers/system.py::
    # _apply_wind_refinements). Never derived from cache/fusion.
    wind_refinements = refinements_from(gps, true_wind)

    if not true_wind:
        # No sensor and no station/model source: nothing wind-dependent is
        # computed, maneuvers included (see analyze_session).
        return SessionContext(
            gps=gps, imu=imu, wind=wind, true_wind=[], avg_twd=None,
            estimated_position=estimated_position, estimated_motion=estimated_motion,
            wind_refinements=wind_refinements, maneuvers=[], track_wind_observations=[],
        )

    true_wind, maneuvers, observations = _refine_wind_with_maneuvers(
        gps, imu, true_wind, tack_wind.observations_from_bundle(raw_wind_bundle),
    )

    return SessionContext(
        gps=gps, imu=imu, wind=wind, true_wind=true_wind, avg_twd=_avg_twd(true_wind),
        estimated_position=estimated_position, estimated_motion=estimated_motion,
        wind_refinements=wind_refinements, maneuvers=maneuvers,
        track_wind_observations=tack_wind.to_payload(observations),
    )


# Re-classification stops once the session's mean wind moves less than this
# between passes, or after MAX_REFINE_PASSES whatever happens.
REFINE_CONVERGED_DEG = 2.0
MAX_REFINE_PASSES = 4


def _refine_wind_with_maneuvers(gps: list, imu: list, model_wind: list, bundle_observations: list):
    """Model wind → ``(true_wind, maneuvers, own observations)``, iterated to
    a fixed point.

    Tack vs gybe vs course change is decided against the wind axis, and the
    tacks are what correct that axis (``processing/tack_wind.py``) — so one
    pass classifies against the very wind being corrected. Each pass
    re-classifies against the previous pass's corrected wind and re-blends
    from the *model* wind (never on top of an earlier blend, which would count
    the same tacks twice), until the mean direction settles. Detection itself
    is wind-agnostic, so only the labels and wind-relative features change.

    When a pass finds no tack at all, the model may be too far off for the
    classifier to see one: ``seed_observations`` then moves the axis for the
    next pass only. Seeds never reach the result — if the classifier still
    calls nothing a tack, the model wind stands.

    Emitted for sensor sessions too: a bisector is read off GPS headings alone,
    so it is independent evidence for the neighbours that receive it; sensor
    rows themselves are never blended."""
    def blend(evidence: list) -> list:
        return tack_wind.blend_observations(
            gps, [dict(r) for r in model_wind], evidence + bundle_observations)

    true_wind = model_wind
    axis = _avg_twd(model_wind)
    for _ in range(MAX_REFINE_PASSES):
        maneuvers = detect_maneuvers(gps, imu, axis, true_wind)
        observations = tack_wind.observations_from_maneuvers(gps, maneuvers)
        seeds = [] if observations else tack_wind.seed_observations(gps, maneuvers, axis)
        true_wind = blend(observations or seeds)
        new_axis = _avg_twd(true_wind)
        moved = abs(((new_axis - axis + 180.0) % 360.0) - 180.0)
        axis = new_axis
        if not seeds and moved < REFINE_CONVERGED_DEG:
            return true_wind, maneuvers, observations

    if seeds:
        # The seeds never turned into tacks the classifier agrees with: drop
        # them, and label the maneuvers against the wind that actually stands.
        true_wind = blend([])
        maneuvers = detect_maneuvers(gps, imu, _avg_twd(true_wind), true_wind)
        return true_wind, maneuvers, []
    return true_wind, maneuvers, observations


def _avg_twd(true_wind: list) -> Optional[float]:
    twds = [tw["twd_deg"] for tw in true_wind if tw.get("twd_deg") is not None]
    return circular_mean(np.array(twds)) if twds else None


def analyze_session(
    data_dir: Path, trim_start: Optional[float] = None, trim_end: Optional[float] = None,
) -> dict:
    """Run full analysis pipeline on a session directory.

    Expects directory structure:
        data_dir/
            gps.json
            imu.json
            wind.json
            pressure.json
            manifest.json

    ``trim_start``/``trim_end`` — see ``load_session_context``; ``None``/
    ``None`` (the default) analyzes the full track."""
    ctx = load_session_context(data_dir, trim_start=trim_start, trim_end=trim_end)
    if ctx is None:
        return {"error": "No GPS data found"}
    gps, imu, wind = ctx.gps, ctx.imu, ctx.wind

    # What needs no wind. Every key the backend reads is always present, so a
    # re-analysis that loses its wind also clears the stale wind-dependent rows.
    base = {
        "summary": _session_summary(gps),
        "session_stats": session_statistics(gps, wind, imu),
        # Persisted separately as their own blob artifacts by the caller
        # (handler.py::process_analyze_prefix) — not written directly here
        # since analyze_session stays a pure function (dict in, dict out).
        # The caller pops these back out before posting the rest of `result`
        # to the backend, so they're stored once, not duplicated into
        # analysis.json too.
        "estimated_position": ctx.estimated_position,
        "estimated_motion": ctx.estimated_motion,
        "wind_refinements": ctx.wind_refinements,
        # Stored per session by the backend and shared with neighbouring
        # sessions' wind_cache.json (backend/services/track_wind.py).
        "track_wind_observations": ctx.track_wind_observations,
        "analysis_unavailable": None,
    }
    if not ctx.true_wind:
        return {**base, **_no_wind_analysis(), "analysis_unavailable": "no_wind_data"}

    true_wind = ctx.true_wind
    maneuvers = ctx.maneuvers
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
    violin = violin_plot_data(maneuvers)
    correlations = correlation_matrix(gps, true_wind, imu)
    leg_ranking = leg_performance_ranking(legs)

    return {
        **base,
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
        "violin": violin,
        "correlations": correlations,
        "leg_ranking": leg_ranking,
    }


def _no_wind_analysis() -> dict:
    """The wind-dependent half of an analysis, empty: what a session with
    neither an onboard sensor nor any station/model source gets. The product
    decision is no analysis rather than one against a guessed direction with
    no speed."""
    return {
        "maneuvers": [],
        "maneuver_summary": None,
        "legs": [],
        "leg_comparison": None,
        "polar": None,
        "polar_points": [],
        "polar_target": [],
        "vmg_series": [],
        "true_wind": [],
        "violin": None,
        "correlations": None,
        "leg_ranking": None,
    }


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
