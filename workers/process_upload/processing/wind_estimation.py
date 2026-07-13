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
pre-picked series.

Two strategies ship:

- ``sensor_cache_gps`` (legacy): picks ONE source per waypoint
  (``_flatten_bundle``) — no blending.
- ``weighted_fusion`` (default): blends every source per waypoint with the
  shared ``xgsail_windfusion`` weighting (``_fuse_bundle``), so a real
  station, several Open-Meteo models, and a grid estimate all contribute in
  proportion to their reliability instead of the first one winning.
"""

import math
from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np

from xgsail_windfusion import source_weight, weighted_wind_mean

from .models import GpsPoint, ImuReading, WindReading
from .wind import (
    _to_timestamp,
    compute_true_wind_series,
    estimate_wind_axis_from_gps,
    estimate_wind_from_gps,
    true_wind_from_cached,
)

WindEstimator = Callable[
    ["list[GpsPoint]", "list[WindReading]", "Optional[list[ImuReading]]", "list[dict]"],
    "list[dict]",
]

# Open-Meteo model name -> reliability class for ``source_weight``. Regional
# high-resolution models are trusted over the global fallback (see
# ``MODEL_CANDIDATES`` in ``backend/services/wind_providers/open_meteo.py``).
_MODEL_SOURCE_TYPE = {
    "icon_d2": "model_regional",
    "icon_eu": "model_regional",
    "gfs_seamless": "model_global",
    "ecmwf_ifs025": "model_global",
}


def _flatten_bundle(raw_wind_bundle: "list[dict]") -> "list[dict]":
    """Reduce the rich per-waypoint bundle to the flat, lat/lng-tagged rows
    ``true_wind_from_cached`` expects — real station data if a waypoint has
    it, else the first Open-Meteo candidate model with data, else an
    existing grid estimate. This is *a* choice (first source wins, no
    blending) kept for the legacy strategy; ``_fuse_bundle`` blends instead."""
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


def _series_arrays(rows: "list[dict]", *, time_key: str = "observed_at"):
    """Turn a source's rows into sorted numpy arrays ``(times, sin, cos, tws)``
    ready for time-interpolation — direction as sin/cos so it interpolates on
    the circle, not linearly across the 0/360 wrap. ``None`` if the source has
    no usable rows."""
    triples = []
    for r in rows:
        twd, tws, t = r.get("twd_deg"), r.get("tws_kts"), r.get(time_key)
        if twd is None or tws is None or t is None:
            continue
        triples.append((_to_timestamp(t), twd, tws))
    if not triples:
        return None
    triples.sort(key=lambda x: x[0])
    times = np.array([x[0] for x in triples], dtype=float)
    sin_a = np.array([math.sin(math.radians(x[1])) for x in triples], dtype=float)
    cos_a = np.array([math.cos(math.radians(x[1])) for x in triples], dtype=float)
    tws_a = np.array([x[2] for x in triples], dtype=float)
    return times, sin_a, cos_a, tws_a


def _interp_at(arrays, t: float):
    """Interpolate a prepared source series to time ``t`` (circular for
    direction). ``None`` outside the source's own time span — a source never
    contributes where it has no data (no extrapolation)."""
    times, sin_a, cos_a, tws_a = arrays
    if t < times[0] or t > times[-1]:
        return None
    s = float(np.interp(t, times, sin_a))
    c = float(np.interp(t, times, cos_a))
    tws = float(np.interp(t, times, tws_a))
    twd = (math.degrees(math.atan2(s, c)) + 360.0) % 360.0
    return twd, tws


def _fuse_bundle(raw_wind_bundle: "list[dict]") -> "list[dict]":
    """Blend every source of each waypoint into one fused time series, in the
    same flat shape ``_flatten_bundle`` returns (so ``true_wind_from_cached``
    can interpolate it onto the track unchanged). For each waypoint:

    1. prepare each source (real station, every Open-Meteo model, grid) as an
       interpolatable series with a reliability weight from
       ``xgsail_windfusion.source_weight``;
    2. on the union of all their timestamps, interpolate each source to that
       time and ``weighted_wind_mean`` the ones that cover it.

    A time covered by a single source still yields that source's value (a
    one-element weighted mean) — so this never drops data the pick-first
    flatten would have kept, it only *adds* blending where sources overlap."""
    flat = []
    for wp in raw_wind_bundle or []:
        lat, lng = wp.get("lat"), wp.get("lng")

        # (source_type, weight_kwargs, prepared_arrays) for every source present.
        sources = []

        stations = wp.get("real_stations") or []
        arrays = _series_arrays(stations)
        if arrays is not None:
            # All rows are the same station → one distance for the whole series.
            sources.append(("real_station", {"distance_km": stations[0].get("distance_km")}, arrays))

        for model, rows in (wp.get("model_candidates") or {}).items():
            arrays = _series_arrays(rows or [])
            if arrays is not None:
                # Open-Meteo is queried AT the waypoint → no spatial offset.
                sources.append((_MODEL_SOURCE_TYPE.get(model, "model_global"), {}, arrays))

        grid = wp.get("grid_estimates") or []
        arrays = _series_arrays(grid, time_key="time_bucket")
        if arrays is not None:
            confs = [g.get("confidence") for g in grid if g.get("confidence") is not None]
            grid_conf = (sum(confs) / len(confs)) if confs else None
            sources.append(("grid_estimate", {"internal_confidence": grid_conf}, arrays))

        if not sources:
            continue

        all_times = sorted({float(t) for _, _, arr in sources for t in arr[0]})
        for t in all_times:
            contributions = []
            for source_type, weight_kwargs, arrays in sources:
                interp = _interp_at(arrays, t)
                if interp is None:
                    continue
                twd, tws = interp
                contributions.append((twd, tws, source_weight(source_type, **weight_kwargs)))
            fused = weighted_wind_mean(contributions)
            if fused is None:
                continue
            twd, tws, confidence = fused
            flat.append({
                "station_lat": lat,
                "station_lng": lng,
                "observed_at": t,  # epoch seconds; _to_timestamp() handles floats
                "twd_deg": twd,
                "tws_kts": tws,
                # Total fused weight, used to balance the low-weight GPS-axis
                # nudge below; ignored by true_wind_from_cached.
                "confidence": confidence,
            })
    return flat


def _nudge_with_gps_axis(fused_rows: "list[dict]", axis_deg: float, gps_confidence: float) -> "list[dict]":
    """Fold a GPS-derived wind *axis* into already-fused rows as a low-weight
    direction-only correction. For each row the axis (a line, ambiguous by
    180°) is resolved to whichever end is nearer the row's fused direction —
    i.e. the speed-bearing sources break the tie — then blended in with a
    small weight (``gps_estimate`` prior × the axis's own confidence). Speed
    is never touched: the GPS track says nothing about wind speed.

    Only ever called when ``fused_rows`` is non-empty, so the GPS signal
    refines an existing estimate and never stands as the wind on its own."""
    gps_weight = source_weight("gps_estimate", internal_confidence=gps_confidence)
    for r in fused_rows:
        fused_twd = r["twd_deg"]
        # Resolve the 180° ambiguity against the fused (speed-bearing) direction.
        candidates = (axis_deg % 360.0, (axis_deg + 180.0) % 360.0)
        resolved = min(candidates, key=lambda c: abs((c - fused_twd + 180.0) % 360.0 - 180.0))
        # Unit-vector (direction-only) weighted blend: existing weighted by its
        # own fused confidence, GPS by its small weight.
        blended = weighted_wind_mean([
            (fused_twd, 1.0, r.get("confidence") or 1.0),
            (resolved, 1.0, gps_weight),
        ])
        if blended is not None:
            r["twd_deg"] = blended[0]
    return fused_rows


def _gps_estimate_series(gps: "list[GpsPoint]") -> "list[dict]":
    """Last-resort tier shared by every strategy: a rough wind *direction*
    from the GPS tack pattern alone, normalized to the standard series shape.
    No speed (``tws_kts``/``twa_deg`` left ``None``), tagged
    ``"gps_estimate"``. Empty if the track doesn't support even that."""
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


def _cache_series(gps: "list[GpsPoint]", flat_rows: "list[dict]", *, source: str) -> "list[dict]":
    """Interpolate flat, lat/lng-tagged wind rows onto the track via the
    shared ``true_wind_from_cached``, retagging ``source`` so a plain
    pick-first ``"cache"`` series and a blended ``"fusion"`` series are
    distinguishable downstream. Empty if there are no rows to interpolate."""
    if not flat_rows:
        return []
    series = true_wind_from_cached(gps, flat_rows)
    for r in series:
        r["source"] = source
    return series


def sensor_then_cache_then_gps(
    gps: "list[GpsPoint]",
    wind: "list[WindReading]",
    imu: "Optional[list[ImuReading]]",
    raw_wind_bundle: "list[dict]",
) -> "list[dict]":
    """Legacy behavior, in preference order:

    1. onboard wind sensor (measured apparent -> true),
    2. raw wind bundle reduced to ONE source per waypoint (``_flatten_bundle``,
       no blending) interpolated onto the track,
    3. a rough direction estimated from the GPS tack pattern alone."""
    true_wind = compute_true_wind_series(gps, wind, imu)
    if true_wind:
        return true_wind
    cached = _cache_series(gps, _flatten_bundle(raw_wind_bundle), source="cache")
    if cached:
        return cached
    return _gps_estimate_series(gps)


def weighted_fusion(
    gps: "list[GpsPoint]",
    wind: "list[WindReading]",
    imu: "Optional[list[ImuReading]]",
    raw_wind_bundle: "list[dict]",
) -> "list[dict]":
    """Default behavior. Same tiering as ``sensor_then_cache_then_gps``, but
    tier 2 *blends* every source per waypoint (``_fuse_bundle``) instead of
    picking the first, weighting each by reliability (source type, station
    distance, grid confidence) via the shared ``xgsail_windfusion``.

    Tier 1 (onboard sensor) is unchanged and still the sole feeder of the
    ``wind_estimates`` grid via ``refinements_from`` — the blended tier is
    tagged ``"fusion"`` (not ``"sensor"``), so models/grid never get
    re-injected into the grid as if they were a direct measurement.

    When the GPS track is a genuine windward beat/run
    (``estimate_wind_axis_from_gps``), its tack axis nudges the fused
    *direction* with a small weight, its 180° ambiguity resolved against the
    speed-bearing sources — never on its own (only applied when the bundle
    already produced a fused series)."""
    true_wind = compute_true_wind_series(gps, wind, imu)
    if true_wind:
        return true_wind
    fused_rows = _fuse_bundle(raw_wind_bundle)
    if fused_rows:
        axis = estimate_wind_axis_from_gps(gps)
        if axis is not None:
            fused_rows = _nudge_with_gps_axis(fused_rows, axis[0], axis[1])
    fused = _cache_series(gps, fused_rows, source="fusion")
    if fused:
        return fused
    return _gps_estimate_series(gps)


STRATEGIES: "dict[str, WindEstimator]" = {
    "sensor_cache_gps": sensor_then_cache_then_gps,
    "weighted_fusion": weighted_fusion,
}

# Change this (and rebuild the worker image) to switch strategies.
ACTIVE_STRATEGY = "weighted_fusion"


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
    from a blended/cache/GPS-only estimate: those aren't measurements,
    refining the grid with them would poison it with the very estimate it's
    meant to improve on.

    Emits ``gust_kts`` (``None`` when the sensor series carries none) so the
    field name matches what ``routers/system.py::_apply_wind_refinements``
    reads on the backend side."""
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
            "gust_kts": tw.get("gust_kts"),
            "source": "onboard_sensor",
        })
    return out
