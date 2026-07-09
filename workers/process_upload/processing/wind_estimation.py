"""Pluggable strategies for producing a session's ``true_wind`` series from
whatever signals happen to be available — the worker-side half of wind
estimation (see ``backend/services/wind_model_selection.py``/``wind_lookup.
gather_raw_wind`` for the other half: pure acquisition of every raw
candidate, no picking, on the backend side).

Add a strategy by writing a function with the ``WindEstimator`` signature
and registering it below; swap ``ACTIVE_STRATEGY`` to experiment (constant,
not env-configurable — change it and rebuild the worker image).

Every strategy must return the same shape regardless of which signal it
used: ``list[{timestamp, tws_kts, twa_deg, twd_deg, boat_speed_kts,
heading_deg, source, ...}]`` — this is what ``segment_legs``/
``generate_polar``/``compute_vmg_series``/``detect_maneuvers`` all consume.

``raw_wind_bundle`` (from the backend's ``wind_cache.json``) is a list of
per-waypoint bundles: ``[{lat, lng, real_stations: [...],
model_candidates: {model_name: [...]}, grid_estimates: [...]}, ...]`` — a
strategy sees *everything* fetched for the session's track, not a single
pre-picked series. The default strategy below still ends up choosing one
series per waypoint (see ``_flatten_bundle``) to keep today's behavior
unchanged; a smarter strategy can use the full bundle instead (e.g. weight
by distance/model, cross-check with the GPS track).
"""

from datetime import datetime, timezone
from typing import Callable, Optional

from .models import GpsPoint, ImuReading, WindReading
from .wind import compute_true_wind_series, estimate_wind_from_gps, true_wind_from_cached

WindEstimator = Callable[
    ["list[GpsPoint]", "list[WindReading]", "Optional[list[ImuReading]]", "list[dict]"],
    "list[dict]",
]


def _flatten_bundle(raw_wind_bundle: "list[dict]") -> "list[dict]":
    """Reduce the rich per-waypoint bundle to the flat, lat/lng-tagged rows
    ``true_wind_from_cached`` expects — real station data if a waypoint has
    it, else the first Open-Meteo candidate model with data, else an
    existing grid estimate. This is *a* choice, not the only sensible one:
    the unflattened bundle is available to any strategy that wants to do
    better (see module docstring)."""
    flat = []
    for wp in raw_wind_bundle or []:
        lat, lng = wp.get("lat"), wp.get("lng")
        rows = wp.get("real_stations") or []
        if not rows:
            for model_rows in (wp.get("model_candidates") or {}).values():
                if model_rows:
                    rows = model_rows
                    break
        if not rows:
            rows = wp.get("grid_estimates") or []
        for r in rows:
            flat.append({
                "station_lat": lat,
                "station_lng": lng,
                "observed_at": r.get("observed_at") or r.get("time_bucket"),
                "twd_deg": r.get("twd_deg"),
                "tws_kts": r.get("tws_kts"),
                "gust_kts": r.get("gust_kts"),
            })
    return flat


def sensor_then_cache_then_gps(
    gps: "list[GpsPoint]",
    wind: "list[WindReading]",
    imu: "Optional[list[ImuReading]]",
    raw_wind_bundle: "list[dict]",
) -> "list[dict]":
    """Today's behavior, in preference order:

    1. onboard wind sensor (measured apparent -> true),
    2. raw wind bundle (real station / Open-Meteo / grid estimate, flattened
       — see ``_flatten_bundle``) interpolated onto the track,
    3. a rough direction estimated from the GPS tack pattern alone.

    Tier 3 is normalized to the same ``list[dict]`` shape as the other two
    (constant ``twd_deg`` per point, ``tws_kts``/``twa_deg`` left ``None``
    since a GPS-only estimate carries no speed information) so legs/polar/
    VMG get *something* even in that edge case, instead of nothing."""
    true_wind = compute_true_wind_series(gps, wind, imu)
    if true_wind:
        return true_wind

    cached_obs = _flatten_bundle(raw_wind_bundle)
    if cached_obs:
        true_wind = true_wind_from_cached(gps, cached_obs)
        if true_wind:
            return true_wind

    est = estimate_wind_from_gps(gps)
    if est is None:
        return []
    twd, confidence = est
    return [{
        "timestamp": p.timestamp,
        "twd_deg": twd,
        "tws_kts": None,
        "twa_deg": None,
        "boat_speed_kts": p.speed_kts,
        "heading_deg": p.heading_deg,
        "source": "gps_estimate",
        "confidence": confidence,
    } for p in gps]


STRATEGIES: "dict[str, WindEstimator]" = {
    "sensor_cache_gps": sensor_then_cache_then_gps,
}

# Change this (and rebuild the worker image) to switch strategies.
ACTIVE_STRATEGY = "sensor_cache_gps"


def estimate(
    gps: "list[GpsPoint]",
    wind: "list[WindReading]",
    imu: "Optional[list[ImuReading]]",
    raw_wind_bundle: "list[dict]",
) -> "list[dict]":
    return STRATEGIES[ACTIVE_STRATEGY](gps, wind, imu, raw_wind_bundle)


def refinements_from(gps: "list[GpsPoint]", true_wind: "list[dict]") -> "list[dict]":
    """Observations worth feeding back into the backend's ``wind_estimates``
    grid — only when ``true_wind`` came from a real onboard sensor
    (``source == "sensor"``, set by ``compute_true_wind_series``), never
    from a cache or GPS-only guess: those aren't measurements, refining the
    grid with them would poison it with the very estimate it's meant to
    improve on."""
    if not true_wind or true_wind[0].get("source") != "sensor":
        return []
    gps_by_t = {p.timestamp: p for p in gps}
    out = []
    for tw in true_wind:
        p = gps_by_t.get(tw["timestamp"])
        if p is None or tw.get("twd_deg") is None:
            continue
        out.append({
            "lat": p.lat,
            "lng": p.lon,
            "observed_at": datetime.fromtimestamp(tw["timestamp"], tz=timezone.utc).isoformat(),
            "twd_deg": tw.get("twd_deg"),
            "tws_kts": tw.get("tws_kts"),
            "source": "onboard_sensor",
        })
    return out
