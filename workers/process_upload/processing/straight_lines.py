"""Upwind/downwind/reaching leg segmentation and statistics.

Identifies straight-line sailing segments between maneuvers,
classifies them by point of sail, and computes performance stats.
"""

import math

import numpy as np

from .angles import angular_diff
from .maneuvers import _smooth_heading
from .models import GpsPoint, ImuReading, LegType, Maneuver, ManeuverType, StraightLineLeg

# Minimum duration for a leg to be considered (seconds)
MIN_LEG_DURATION_SEC = 15
# Minimum points in a leg
MIN_LEG_POINTS = 5
# Max heading deviation for "straight line" (degrees STD)
MAX_HEADING_STD_DEG = 15.0
# A span between maneuvers is cut where its smoothed heading leaves the running
# mean of the current sub-leg by more than this. Bear-aways and round-ups slower
# than the maneuver detector's turn-rate gate (typical downwind, in waves) would
# otherwise leave one unsteady span that fails the std check as a whole.
SPLIT_HEADING_DEG = 25.0
# Samples (1 Hz) — wide enough to average out wave-induced yaw before splitting.
SPLIT_SMOOTH_WINDOW = 15
# A reach tacked on at both ends was a loosely-trimmed beat (or the wind
# estimate is off): nobody tacks on a beam reach.
IN_BEAT_MAX_TWA_DEG = 95.0
# Likewise a reach gybed on at both ends belongs with the downwind legs.
IN_RUN_MIN_TWA_DEG = 85.0

_CROSSINGS = (ManeuverType.TACK, ManeuverType.GYBE)


def segment_legs(
    gps: list[GpsPoint],
    maneuvers: list[Maneuver],
    true_wind: list[dict] | None = None,
    imu: list[ImuReading] | None = None,
) -> list[StraightLineLeg]:
    """Segment GPS track into straight-line legs between maneuvers.

    Each span between maneuvers is split into steady sub-legs at heading
    change points; sub-legs too short or too curvy are dropped.

    Args:
        gps: GPS track points.
        maneuvers: Detected maneuvers (tacks/gybes/course changes).
        true_wind: True wind series for TWA classification.
        imu: IMU data for heel angle stats.

    Returns:
        List of StraightLineLeg segments.
    """
    if len(gps) < MIN_LEG_POINTS:
        return []

    gps_times = np.array([p.timestamp for p in gps])
    headings = np.array([p.heading_deg for p in gps])

    # Build segment boundaries from maneuver times
    sorted_maneuvers = sorted(maneuvers, key=lambda x: x.start_time)
    crossings = [m for m in sorted_maneuvers if m.maneuver_type in _CROSSINGS]
    boundaries = [gps_times[0]]
    for m in sorted_maneuvers:
        boundaries.append(m.start_time)
        boundaries.append(m.end_time)
    boundaries.append(gps_times[-1])

    wind = None
    if true_wind:
        wind = (np.array([tw["timestamp"] for tw in true_wind]),
                np.array([tw["twa_deg"] for tw in true_wind]))
    heel = None
    if imu:
        heel = (np.array([r.timestamp for r in imu]), np.array([r.heel_deg for r in imu]))

    legs = []
    for i in range(0, len(boundaries) - 1, 2):
        span_start, span_end = boundaries[i], boundaries[i + 1]
        idx = np.flatnonzero((gps_times >= span_start) & (gps_times <= span_end))
        if len(idx) < MIN_LEG_POINTS:
            continue

        pieces = _split_steady(headings[idx])
        for n, (a, b) in enumerate(pieces):
            seg = idx[a:b]
            # Outer edges keep the maneuver times; inner cuts sit on a GPS fix.
            t_start = span_start if n == 0 else gps_times[seg[0]]
            t_end = span_end if n == len(pieces) - 1 else gps_times[seg[-1]]
            if len(seg) < MIN_LEG_POINTS or t_end - t_start < MIN_LEG_DURATION_SEC:
                continue
            heading_std = _circular_std(headings[seg])
            if heading_std > MAX_HEADING_STD_DEG:
                continue
            legs.append(_build_leg(
                [gps[j] for j in seg], t_start, t_end, heading_std,
                crossings, wind, heel,
            ))

    return legs


def _split_steady(headings: np.ndarray) -> list[tuple[int, int]]:
    """Cut a span into ``[a, b)`` index ranges of roughly constant heading.

    Greedy walk over the smoothed heading: a new piece starts where it
    departs from the circular running mean of the current piece by more than
    ``SPLIT_HEADING_DEG``. A steady span comes back as one piece.
    """
    smooth = np.radians(_smooth_heading(headings, SPLIT_SMOOTH_WINDOW))
    pieces, start = [], 0
    sin_sum = cos_sum = 0.0
    for j, h in enumerate(smooth):
        if j > start:
            mean = math.degrees(math.atan2(sin_sum, cos_sum))
            if abs(angular_diff(math.degrees(h), mean)) > SPLIT_HEADING_DEG:
                pieces.append((start, j))
                start, sin_sum, cos_sum = j, 0.0, 0.0
        sin_sum += math.sin(h)
        cos_sum += math.cos(h)
    pieces.append((start, len(smooth)))
    return pieces


def _build_leg(
    seg_gps: list[GpsPoint],
    t_start: float,
    t_end: float,
    heading_std: float,
    crossings: list[Maneuver],
    wind: tuple[np.ndarray, np.ndarray] | None,
    heel: tuple[np.ndarray, np.ndarray] | None,
) -> StraightLineLeg:
    speeds = np.array([p.speed_kts for p in seg_gps])
    distance = _compute_distance_nm(seg_gps)

    avg_vmg = 0.0
    avg_twa = None
    tack = None
    leg_type = LegType.REACH  # default

    if wind is not None:
        tw_times, tw_twa = wind
        seg_twa = tw_twa[(tw_times >= t_start) & (tw_times <= t_end)]
        if len(seg_twa):
            # Sign before the abs() below is which side the wind is on —
            # a straight leg never crosses a tack/gybe (that's a maneuver,
            # segmented out above), so a plain mean is safe here (no
            # wraparound across the +/-180 boundary within one leg).
            tack = "starboard" if float(np.mean(seg_twa)) >= 0 else "port"
            avg_twa = float(np.mean(np.abs(seg_twa)))

            if avg_twa < 70:
                leg_type = LegType.UPWIND
            elif avg_twa > 120:
                leg_type = LegType.DOWNWIND
            else:
                leg_type = LegType.REACH

            avg_vmg = float(np.mean(speeds) * abs(math.cos(math.radians(avg_twa))))

    # Only a tack or gybe says which way the boat is working; a course change
    # or a heading split in between doesn't.
    before = next((m.maneuver_type for m in reversed(crossings) if m.end_time <= t_start), None)
    after = next((m.maneuver_type for m in crossings if m.start_time >= t_end), None)
    is_reach = leg_type == LegType.REACH and avg_twa is not None
    in_beat = is_reach and avg_twa < IN_BEAT_MAX_TWA_DEG and before == after == ManeuverType.TACK
    in_run = is_reach and avg_twa > IN_RUN_MIN_TWA_DEG and before == after == ManeuverType.GYBE

    avg_heel = None
    if heel is not None:
        imu_times, imu_heels = heel
        seg_heel = imu_heels[(imu_times >= t_start) & (imu_times <= t_end)]
        if len(seg_heel):
            avg_heel = float(np.mean(np.abs(seg_heel)))

    return StraightLineLeg(
        leg_type=leg_type,
        start_time=t_start,
        end_time=t_end,
        duration_sec=round(t_end - t_start, 1),
        distance_nm=round(distance, 3),
        avg_speed_kts=round(float(np.mean(speeds)), 2),
        max_speed_kts=round(float(np.max(speeds)), 2),
        avg_vmg_kts=round(avg_vmg, 2),
        avg_heel_deg=round(avg_heel, 1) if avg_heel is not None else None,
        avg_twa_deg=round(avg_twa, 1) if avg_twa is not None else None,
        tack=tack,
        in_beat=in_beat,
        in_run=in_run,
        std_heading_deg=round(heading_std, 1),
        num_points=len(seg_gps),
        start_lat=seg_gps[0].lat,
        start_lon=seg_gps[0].lon,
        end_lat=seg_gps[-1].lat,
        end_lon=seg_gps[-1].lon,
    )


def _circular_std(angles_deg: np.ndarray) -> float:
    """Compute circular standard deviation of angles in degrees."""
    angles_rad = np.radians(angles_deg)
    sin_mean = np.mean(np.sin(angles_rad))
    cos_mean = np.mean(np.cos(angles_rad))
    r = math.sqrt(sin_mean**2 + cos_mean**2)
    if r > 1.0:
        r = 1.0
    if r < 1e-10:
        return 180.0
    return math.degrees(math.sqrt(-2 * math.log(r)))


def _compute_distance_nm(points: list[GpsPoint]) -> float:
    """Sum great-circle distances between consecutive GPS points."""
    total = 0.0
    for i in range(1, len(points)):
        total += _haversine_nm(
            points[i - 1].lat, points[i - 1].lon,
            points[i].lat, points[i].lon,
        )
    return total


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in nautical miles."""
    r = 3440.065  # Earth radius in nautical miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def leg_comparison(legs: list[StraightLineLeg]) -> dict:
    """Compare performance across legs by type."""
    by_type = {}
    for leg_type in LegType:
        typed_legs = [l for l in legs if l.leg_type == leg_type]
        if not typed_legs:
            continue
        speeds = [l.avg_speed_kts for l in typed_legs]
        vmgs = [l.avg_vmg_kts for l in typed_legs]
        by_type[leg_type.value] = {
            "count": len(typed_legs),
            "avg_speed_kts": round(np.mean(speeds), 2),
            "max_speed_kts": round(max(l.max_speed_kts for l in typed_legs), 2),
            "avg_vmg_kts": round(np.mean(vmgs), 2),
            "total_distance_nm": round(sum(l.distance_nm for l in typed_legs), 3),
        }
    return by_type
