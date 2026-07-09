"""Wind direction calculation and true wind estimation.

Computes true wind from apparent wind + boat speed/heading,
with fallback estimation when sensors are unavailable.
"""

import math
from datetime import datetime
from typing import Optional

import numpy as np

from .models import GpsPoint, ImuReading, WindReading
from .straight_lines import _haversine_nm


def _to_timestamp(t) -> float:
    """Convert ISO string or datetime to Unix timestamp."""
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, str):
        # Handle ISO format with Z suffix
        t = t.replace("Z", "+00:00")
        return datetime.fromisoformat(t).timestamp()
    if isinstance(t, datetime):
        return t.timestamp()
    return 0.0


def apparent_to_true_wind(
    aws_kts: float,
    awa_deg: float,
    boat_speed_kts: float,
    heading_deg: float,
) -> tuple[float, float, float]:
    """Convert apparent wind to true wind.

    Args:
        aws_kts: Apparent wind speed in knots.
        awa_deg: Apparent wind angle in degrees (0=bow, positive=starboard).
        boat_speed_kts: Boat speed over ground in knots.
        heading_deg: Boat heading in degrees true.

    Returns:
        Tuple of (true_wind_speed_kts, true_wind_angle_deg, true_wind_direction_deg).
    """
    awa_rad = math.radians(awa_deg)

    # Decompose apparent wind into boat-frame components
    aw_x = aws_kts * math.cos(awa_rad) - boat_speed_kts  # fore-aft
    aw_y = aws_kts * math.sin(awa_rad)  # lateral

    tws_kts = math.sqrt(aw_x**2 + aw_y**2)
    twa_rad = math.atan2(aw_y, aw_x)
    twa_deg = math.degrees(twa_rad)

    # True wind direction (where wind comes FROM, in degrees true)
    twd_deg = (heading_deg + twa_deg + 180) % 360

    return tws_kts, twa_deg, twd_deg


def compute_true_wind_series(
    gps: list[GpsPoint],
    wind: list[WindReading],
    imu: Optional[list[ImuReading]] = None,
) -> list[dict]:
    """Compute true wind for each wind reading, interpolating GPS data.

    Returns list of dicts with keys: timestamp, tws_kts, twa_deg, twd_deg,
    aws_kts, awa_deg, boat_speed_kts, heading_deg.
    """
    if not gps or not wind:
        return []

    gps_times = np.array([_to_timestamp(p.timestamp) for p in gps])
    gps_speeds = np.array([p.speed_kts for p in gps])
    gps_headings = np.array([p.heading_deg for p in gps])

    # Use IMU heading if available (higher rate, more accurate)
    if imu and len(imu) > 10:
        imu_times = np.array([_to_timestamp(r.timestamp) for r in imu])
        imu_headings = np.array([r.heading_deg for r in imu])
    else:
        imu_times = gps_times
        imu_headings = gps_headings

    results = []
    for w in wind:
        t = _to_timestamp(w.timestamp)
        if t < gps_times[0] or t > gps_times[-1]:
            continue

        speed = float(np.interp(t, gps_times, gps_speeds))
        heading = float(np.interp(t, imu_times, imu_headings))

        tws, twa, twd = apparent_to_true_wind(
            w.apparent_speed_kts, w.apparent_angle_deg, speed, heading
        )

        results.append({
            "timestamp": w.timestamp,
            "tws_kts": round(tws, 2),
            "twa_deg": round(twa, 1),
            "twd_deg": round(twd, 1),
            "aws_kts": w.apparent_speed_kts,
            "awa_deg": w.apparent_angle_deg,
            "boat_speed_kts": round(speed, 2),
            "heading_deg": round(heading, 1),
            # A real measurement (onboard sensor) — distinguishes this from
            # "cache"/"gps_estimate" so callers know it's safe to feed back
            # into the wind_estimates grid (see wind_estimation.refinements_from).
            "source": "sensor",
        })

    return results


def true_wind_from_cached(
    gps: list[GpsPoint],
    cached_obs: list[dict],
) -> list[dict]:
    """Build a true-wind series from coarse cached wind observations (a nearby
    weather station / forecast grid) when there is no onboard wind sensor.

    ``cached_obs`` are hourly, sparse rows ``{observed_at, twd_deg, tws_kts,
    station_lat, station_lng}`` (from the backend's ``wind_cache.json``) —
    the backend now samples several points along the track rather than just
    the start, so rows may come from more than one station. For each GPS
    point we pick the spatially nearest station (``station_lat``/
    ``station_lng`` missing → treated as one shared station, for cache files
    written before this field existed), then interpolate its series in time
    — TWS linearly, TWD circularly — and derive TWA from the boat's heading,
    yielding the same dict shape as ``compute_true_wind_series`` so
    polar/VMG/leg analysis can consume it. Marked ``source="cache"`` so
    callers can flag it as modelled rather than measured.
    """
    if not gps or not cached_obs:
        return []

    by_station: dict = {}
    for o in cached_obs:
        if o.get("twd_deg") is None or o.get("tws_kts") is None:
            continue
        key = (o.get("station_lat"), o.get("station_lng"))
        by_station.setdefault(key, []).append(
            (_to_timestamp(o["observed_at"]), o["twd_deg"], o["tws_kts"])
        )
    if not by_station:
        return []

    series = {}
    for key, obs in by_station.items():
        obs.sort(key=lambda x: x[0])
        times = np.array([o[0] for o in obs])
        twd = np.radians([o[1] for o in obs])
        # Circular interpolation of direction: interpolate the unit vector,
        # not the raw degrees (which wrap at 360 and would average 350°+10°
        # to 180°).
        series[key] = (times, np.sin(twd), np.cos(twd), np.array([o[2] for o in obs]))

    single_station = len(series) == 1
    only_key = next(iter(series)) if single_station else None

    results = []
    for p in gps:
        if single_station:
            key = only_key
        else:
            key = min(series, key=lambda k: _haversine_nm(p.lat, p.lon, k[0], k[1]))
        times, obs_sin, obs_cos, obs_tws = series[key]

        t = _to_timestamp(p.timestamp)
        tws = float(np.interp(t, times, obs_tws))
        twd = math.degrees(math.atan2(
            float(np.interp(t, times, obs_sin)),
            float(np.interp(t, times, obs_cos)),
        )) % 360
        # TWA: signed angle of the wind (from) relative to the bow, in (-180,180].
        twa = ((twd - p.heading_deg + 180) % 360) - 180

        results.append({
            "timestamp": t,
            "tws_kts": round(tws, 2),
            "twa_deg": round(twa, 1),
            "twd_deg": round(twd, 1),
            "boat_speed_kts": round(p.speed_kts, 2),
            "heading_deg": round(p.heading_deg, 1),
            "source": "cache",
        })

    return results


def estimate_wind_from_gps(
    gps: list[GpsPoint],
    min_speed_kts: float = 2.0,
) -> Optional[tuple[float, float]]:
    """Fallback: estimate true wind direction from GPS tracks.

    Assumes upwind legs have lower speeds and clusters heading around
    the wind direction. Returns (estimated_twd_deg, confidence 0-1).
    """
    if len(gps) < 60:
        return None

    speeds = np.array([p.speed_kts for p in gps])
    headings = np.array([p.heading_deg for p in gps])

    # Filter stationary points
    mask = speeds > min_speed_kts
    if mask.sum() < 30:
        return None

    headings_rad = np.radians(headings[mask])
    speeds_filt = speeds[mask]

    # Low speed points are more likely upwind - weight them
    median_speed = np.median(speeds_filt)
    upwind_mask = speeds_filt < median_speed
    upwind_headings = headings_rad[upwind_mask]

    if len(upwind_headings) < 10:
        return None

    # Find the heading that upwind legs cluster around (two tacks)
    # Use circular mean of upwind headings ± 180
    sin_sum = np.sum(np.sin(2 * upwind_headings))  # double angle to find axis
    cos_sum = np.sum(np.cos(2 * upwind_headings))
    axis_rad = math.atan2(sin_sum, cos_sum) / 2
    estimated_twd = math.degrees(axis_rad) % 360

    # Confidence based on how bimodal the upwind headings are
    spread = np.std(np.cos(upwind_headings - axis_rad))
    confidence = min(1.0, max(0.0, 1.0 - spread))

    return estimated_twd, confidence


def smooth_wind_direction(
    twd_series: list[float],
    window: int = 30,
) -> list[float]:
    """Smooth true wind direction using circular moving average."""
    if len(twd_series) < window:
        return twd_series

    twd_rad = np.radians(twd_series)
    sin_vals = np.sin(twd_rad)
    cos_vals = np.cos(twd_rad)

    kernel = np.ones(window) / window
    sin_smooth = np.convolve(sin_vals, kernel, mode="same")
    cos_smooth = np.convolve(cos_vals, kernel, mode="same")

    smoothed = np.degrees(np.arctan2(sin_smooth, cos_smooth)) % 360
    return smoothed.tolist()
