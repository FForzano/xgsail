"""Pluggable, JOINT estimation of a session's position (lat/lon) and motion
(speed/heading) from raw records — two distinct output series (not fused
into one blob, since they're conceptually different quantities you may want
to persist/inspect separately), but computed together in one pass, not by
two independently-invoked strategies. That's deliberate: a real joint
algorithm (e.g. a Kalman filter fusing GPS fixes with heading/speed into one
state estimate) can't cleanly split "estimate my position" from "estimate my
velocity" into two separately-callable steps without losing the coupling
between them — position and motion here are two views of the same
underlying state, not two unrelated computations that happen to share input.

This is a processing seam, not a parsing one: it takes records already
extracted from whatever source format (GPX via ``services/gpx.py``, device
CSV via ``handler.py``) and normalized into the on-disk ``gps.json`` dict
shape — it does not touch raw file parsing.

Add a strategy: a function ``(records) -> (position, motion)`` with
``position: list[{timestamp, lat, lon, fix_quality}]`` and
``motion: list[{timestamp, speed_kts, heading_deg}]``; register it in
``STRATEGIES``, swap ``ACTIVE_STRATEGY`` to experiment (constant, not
env-configurable — change it and rebuild the worker image).
"""

from datetime import datetime
from typing import Callable

from .models import GpsPoint

TrackEstimator = Callable[["list[dict]"], "tuple[list[dict], list[dict]]"]


def to_timestamp(t) -> float:
    """Convert ISO string or datetime to Unix timestamp."""
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, str):
        t = t.replace("Z", "+00:00")
        return datetime.fromisoformat(t).timestamp()
    if isinstance(t, datetime):
        return t.timestamp()
    return 0.0


def parse_as_is(records: "list[dict]") -> "tuple[list[dict], list[dict]]":
    """Today's behavior: trust every fix verbatim, tolerant of a few
    field-name variants across sources (GPX vs. E1 vs. S1 CSV) — no
    filtering, smoothing, or fusion of any kind. Position and motion are
    trivial projections of the same record here; a real joint algorithm
    would derive them together from shared internal state instead."""
    position, motion = [], []
    for r in records:
        if "timestamp" not in r and "t" not in r:
            continue
        t = to_timestamp(r.get("timestamp", r.get("t", "")))
        position.append({
            "timestamp": t,
            "lat": r.get("lat", r.get("latitude", 0)),
            "lon": r.get("lon", r.get("longitude", 0)),
            "fix_quality": r.get("fix_quality", r.get("fix", 0)),
        })
        motion.append({
            "timestamp": t,
            "speed_kts": r.get("speed_kts", r.get("speed_kn", r.get("speed", 0))),
            "heading_deg": r.get("heading_deg", r.get("course", r.get("heading", 0))),
        })
    return position, motion


STRATEGIES: "dict[str, TrackEstimator]" = {
    "as_is": parse_as_is,
}

# Change this (and rebuild the worker image) to switch strategies.
ACTIVE_STRATEGY = "as_is"


def estimate(records: "list[dict]") -> "tuple[list[dict], list[dict]]":
    return STRATEGIES[ACTIVE_STRATEGY](records)


def merge(position: "list[dict]", motion: "list[dict]") -> "list[GpsPoint]":
    """Recombine the two series into the ``GpsPoint`` shape the rest of the
    pipeline (maneuvers/legs/wind/vmg/polar) already consumes, unchanged.

    Paired by index when both series have the same length — true for every
    strategy that (like ``parse_as_is`` above) derives them from one pass
    over the same records in the same order, and the only way to keep two
    points that happen to share a timestamp (real GPS data has these) from
    silently collapsing onto the same motion values. Falls back to an
    exact-timestamp lookup for a future estimator that samples position and
    motion at genuinely different rates (duplicate timestamps there would
    still collapse to the last one seen — a real interpolation, not this
    plain zip, would be needed to do better)."""
    if len(position) == len(motion):
        return [GpsPoint(
            timestamp=p["timestamp"],
            lat=p["lat"],
            lon=p["lon"],
            speed_kts=m["speed_kts"],
            heading_deg=m["heading_deg"],
            fix_quality=p.get("fix_quality", 0),
        ) for p, m in zip(position, motion)]

    motion_by_t = {m["timestamp"]: m for m in motion}
    points = []
    for p in position:
        m = motion_by_t.get(p["timestamp"])
        if m is None:
            continue
        points.append(GpsPoint(
            timestamp=p["timestamp"],
            lat=p["lat"],
            lon=p["lon"],
            speed_kts=m["speed_kts"],
            heading_deg=m["heading_deg"],
            fix_quality=p.get("fix_quality", 0),
        ))
    return points
