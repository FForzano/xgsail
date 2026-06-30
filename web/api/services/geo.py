"""Geodesy + time helpers (flat-earth / great-circle approximations).

Pure functions, no I/O — shared by GPX parsing and course auto-suggestion.
"""

import math
from datetime import datetime

EARTH_RADIUS_M = 6_371_000.0
METERS_PER_DEG_LAT = 111_320.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, degrees in [0, 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def meters_per_deg_lat() -> float:
    return METERS_PER_DEG_LAT


def meters_per_deg_lon(lat: float) -> float:
    return METERS_PER_DEG_LAT * math.cos(math.radians(lat))


def offset_meters(lat: float, lon: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    """(lat, lon) offset from a point by bearing+distance, flat-earth approx."""
    dx = dist_m * math.sin(math.radians(bearing_deg))
    dy = dist_m * math.cos(math.radians(bearing_deg))
    dlat = dy / meters_per_deg_lat()
    dlon = dx / meters_per_deg_lon(lat)
    return lat + dlat, lon + dlon


def mean_angle_deg(angles: list[float]) -> float:
    """Circular mean of angles in degrees."""
    if not angles:
        return 0.0
    xs = sum(math.cos(math.radians(a)) for a in angles)
    ys = sum(math.sin(math.radians(a)) for a in angles)
    return (math.degrees(math.atan2(ys, xs)) + 360.0) % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    """Smallest signed difference a-b, in degrees, in [-180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0


def iso_diff_seconds(end: str, start: str) -> float:
    """Difference in seconds between two ISO timestamps (0 on parse error)."""
    try:
        fmt = "%Y-%m-%dT%H:%M:%S"
        start_clean = start.replace("Z", "").split(".")[0]
        end_clean = end.replace("Z", "").split(".")[0]
        start_dt = datetime.strptime(start_clean, fmt)
        end_dt = datetime.strptime(end_clean, fmt)
        return (end_dt - start_dt).total_seconds()
    except Exception:
        return 0


def points_near(points: list[dict], iso_target: str, window_sec: float = 30.0) -> list[dict]:
    """Return points whose ``t`` is within ``window_sec`` of ``iso_target``."""
    out = []
    for p in points:
        t = p.get("t", "")
        if not t:
            continue
        if abs(iso_diff_seconds(t, iso_target)) <= window_sec:
            out.append(p)
    return out
