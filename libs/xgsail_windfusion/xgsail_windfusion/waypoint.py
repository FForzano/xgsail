"""Point fusion of one ``wind_cache.json`` waypoint bundle — the per-place,
per-instant estimate both the worker (the whole session's ``true_wind``) and
the backend (a single point/time for the live map) must agree on, which is why
it lives here rather than in either of them.

A waypoint is ``{lat, lng, real_stations, model_candidates, grid_estimates,
track_observations}`` exactly as ``backend/services/wind_lookup.gather_raw_wind``
builds it. Every source is interpolated in time (direction on the circle) and
the ones covering the requested instant are combined with
``weighted_wind_mean``/``source_weight``. A source never extrapolates outside
its own time span: past its last reading it simply stops contributing.

Timestamps may be epoch seconds, ISO-8601 strings or ``datetime`` objects —
the backend hands over datetimes, the worker reads strings back from JSON. A
naive one is taken as UTC.
"""

import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from . import (
    MEASUREMENT_SOURCES,
    TIME_DECAY_SECONDS,
    measurement_dominance,
    source_weight,
    weighted_wind_mean,
)

# Open-Meteo model name -> reliability class for ``source_weight``. Regional
# high-resolution models are trusted over the global fallback (see
# ``MODEL_CANDIDATES`` in ``backend/services/wind_providers/open_meteo.py``).
# A model not listed here is weighed as a global one.
MODEL_SOURCE_TYPE: "dict[str, str]" = {
    "icon_d2": "model_regional",
    "icon_eu": "model_regional",
    "gfs_seamless": "model_global",
    "ecmwf_ifs025": "model_global",
}

EARTH_RADIUS_KM = 6371.0

# Below this interpolated mean speed a source's gust/mean ratio is noise (a
# 0.3 kn reading with a 4 kn gust is a factor of 13), so it is left out of the
# gust factor rather than allowed to blow it up.
GUST_FACTOR_MIN_TWS_KTS = 1.0


@dataclass(frozen=True)
class FusedWind:
    twd_deg: float
    tws_kts: float
    # ``tws_kts`` times the weighted mean gust factor (gust / mean wind) of the
    # sources that report a gust, never below ``tws_kts``; ``None`` if none do.
    gust_kts: Optional[float]
    # Total weight that contributed (see ``weighted_wind_mean``), not normalised.
    confidence: float
    # ``(source_type, name, weight)`` per contributing source; ``name`` is the
    # station name/id, the model name, or ``None`` for the grid estimate.
    contributions: "tuple[tuple[str, Optional[object], float], ...]"


@dataclass(frozen=True)
class WindSource:
    """One source prepared for time interpolation: sorted ``times`` with the
    direction as sin/cos so it interpolates on the circle, not across the
    0/360 wrap. ``gust_times``/``gusts`` hold only the rows reporting a gust."""
    source_type: str
    name: Optional[object]
    weight: float
    times: "list[float]"
    sin: "list[float]"
    cos: "list[float]"
    tws: "list[float]"
    gust_times: "list[float]"
    gusts: "list[float]"
    # From the point of interest; ``None`` for a source queried at the point.
    distance_km: Optional[float] = None


def to_epoch(t) -> Optional[float]:
    """Epoch seconds from an epoch number, an ISO-8601 string or a datetime;
    ``None`` for anything unparseable. Naive values are UTC."""
    if isinstance(t, bool):
        return None
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, str):
        try:
            t = datetime.fromisoformat(t.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(t, datetime):
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.timestamp()
    return None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def station_groups(rows: "list[dict]") -> "list[tuple[Optional[float], list[dict]]]":
    """Split a waypoint's ``real_stations`` rows into one group per station,
    as ``(distance_km, rows)`` in first-seen order. Caches written before
    multi-station support carry no ``station_id``, so the key falls back to
    the station's coordinates — an old single-station cache still yields
    exactly one group with exactly one distance. Grouping first matters:
    interpolating two stations' rows as one series zig-zags between them."""
    groups: "dict[object, list[dict]]" = {}
    for r in rows:
        key = r.get("station_id")
        if key is None:
            key = (r.get("station_lat"), r.get("station_lng"))
        groups.setdefault(key, []).append(r)
    return [(g[0].get("distance_km"), g) for g in groups.values()]


def _interp(t: float, xs: "list[float]", ys: "list[float]") -> float:
    """Linear interpolation for ``xs[0] <= t <= xs[-1]`` — same formula as
    ``numpy.interp`` so the worker's numbers did not move when it switched."""
    j = bisect_right(xs, t) - 1
    if j >= len(xs) - 1:
        return ys[-1]
    slope = (ys[j + 1] - ys[j]) / (xs[j + 1] - xs[j])
    return slope * (t - xs[j]) + ys[j]


def _prepare(source_type: str, name, weight: float, rows: "list[dict]",
             time_key: str = "observed_at",
             distance_km: Optional[float] = None) -> Optional[WindSource]:
    parsed = []
    for r in rows:
        twd, tws = r.get("twd_deg"), r.get("tws_kts")
        t = to_epoch(r.get(time_key))
        if twd is None or tws is None or t is None:
            continue
        parsed.append((t, twd, tws, r.get("gust_kts")))
    if not parsed:
        return None
    parsed.sort(key=lambda x: x[0])
    with_gust = [(p[0], p[3]) for p in parsed if p[3] is not None]
    return WindSource(
        source_type=source_type, name=name, weight=weight,
        times=[p[0] for p in parsed],
        sin=[math.sin(math.radians(p[1])) for p in parsed],
        cos=[math.cos(math.radians(p[1])) for p in parsed],
        tws=[float(p[2]) for p in parsed],
        gust_times=[g[0] for g in with_gust],
        gusts=[float(g[1]) for g in with_gust],
        distance_km=distance_km,
    )


def prepare_sources(waypoint: dict) -> "list[WindSource]":
    """Every source of a waypoint with usable rows, each with its reliability
    weight: one per real station (decayed by its own distance), one per
    Open-Meteo model (queried at the waypoint → no spatial offset), and the
    grid estimate (scaled by its mean confidence)."""
    sources = []
    for distance_km, rows in station_groups(waypoint.get("real_stations") or []):
        first = rows[0]
        name = first.get("station_name") or first.get("station_id")
        src = _prepare("real_station", name,
                       source_weight("real_station", distance_km=distance_km), rows,
                       distance_km=distance_km)
        if src is not None:
            sources.append(src)

    for model, rows in (waypoint.get("model_candidates") or {}).items():
        source_type = MODEL_SOURCE_TYPE.get(model, "model_global")
        src = _prepare(source_type, model, source_weight(source_type), rows or [])
        if src is not None:
            sources.append(src)

    grid = waypoint.get("grid_estimates") or []
    confs = [g.get("confidence") for g in grid if g.get("confidence") is not None]
    grid_conf = (sum(confs) / len(confs)) if confs else None
    src = _prepare("grid_estimate", None,
                   source_weight("grid_estimate", internal_confidence=grid_conf),
                   grid, time_key="time_bucket")
    if src is not None:
        sources.append(src)
    return sources


def fuse_sources(sources: "list[WindSource]", t: float,
                 hold_latest_seconds: float = 0.0) -> Optional[FusedWind]:
    """Fuse prepared sources at epoch ``t``; ``None`` when no source covers it.

    ``hold_latest_seconds`` (default 0, i.e. no change from a source that
    never extrapolates) lets a source whose last reading is up to that many
    seconds *before* ``t`` still contribute, holding its last value and
    decaying its weight by the gap at the shared ``TIME_DECAY_SECONDS``
    scale — for a live "right now" query, where a real station's newest
    reading is typically some minutes old and would otherwise drop out on
    every request. ``_interp`` already clamps to the last value past a
    source's span, so only the weight decay needs the gap; a source still
    ahead of ``t`` (``t < s.times[0]``) is untouched by this.

    Every non-measurement source's weight is then scaled by ``1 - dominance``
    of the strongest measurement covering ``t`` (``measurement_dominance``,
    times the same staleness decay), so near a working station the models
    drop out instead of being averaged in. Only a measurement that actually
    covers ``t`` counts: across a station's data gap the models are back.

    The gust is the fused mean times the weighted mean *gust factor*
    (gust / mean wind) of the sources reporting one, with the same weights.
    Averaging absolute gusts instead would let a model whose weight a
    gust-less nearby station has all but silenced still set the gust on its
    own, unrelated to the station-dominated mean."""
    covering = []
    dominance = 0.0
    for s in sources:
        if t < s.times[0]:
            continue
        gap = max(0.0, t - s.times[-1])
        if gap > hold_latest_seconds:
            continue
        freshness = math.exp(-gap / TIME_DECAY_SECONDS) if gap > 0.0 else 1.0
        covering.append((s, s.weight * freshness))
        if s.source_type in MEASUREMENT_SOURCES:
            dominance = max(dominance, measurement_dominance(s.distance_km) * freshness)

    wind, gust_factors, contributions = [], [], []
    for s, weight in covering:
        if s.source_type not in MEASUREMENT_SOURCES:
            weight *= 1.0 - dominance
        if weight <= 0.0:
            continue  # silenced: it must not show up as a contributor either
        twd = (math.degrees(math.atan2(_interp(t, s.times, s.sin), _interp(t, s.times, s.cos)))
               + 360.0) % 360.0
        tws = _interp(t, s.times, s.tws)
        wind.append((twd, tws, weight))
        if (s.gust_times and s.gust_times[0] <= t <= s.gust_times[-1]
                and tws >= GUST_FACTOR_MIN_TWS_KTS):
            gust_factors.append((_interp(t, s.gust_times, s.gusts) / tws, weight))
        contributions.append((s.source_type, s.name, weight))
    fused = weighted_wind_mean(wind)
    if fused is None:
        return None
    gust = None
    factor_weight = sum(w for _, w in gust_factors)
    if factor_weight > 0.0:
        factor = sum(f * w for f, w in gust_factors) / factor_weight
        # A source reporting a gust below its own mean wind is bad data, not calm.
        gust = fused[1] * max(factor, 1.0)
    return FusedWind(twd_deg=fused[0], tws_kts=fused[1], gust_kts=gust,
                     confidence=fused[2], contributions=tuple(contributions))


def fuse_waypoint(waypoint: dict, t, hold_latest_seconds: float = 0.0) -> Optional[FusedWind]:
    """The fused wind of one waypoint bundle at instant ``t`` (epoch seconds,
    ISO string or datetime); ``None`` if no source covers ``t``. See
    ``fuse_sources`` for ``hold_latest_seconds``."""
    epoch = to_epoch(t)
    if epoch is None:
        return None
    return fuse_sources(prepare_sources(waypoint), epoch, hold_latest_seconds=hold_latest_seconds)


def blend_direction(twd_deg: float, own_weight: float, lat: float, lng: float, t,
                    observations: "list[dict]") -> float:
    """Pull a wind direction toward nearby tack/gybe observations, as a
    direction-only weighted vector mean: the estimate weighs ``own_weight``,
    each observation ``source_weight("gps_tack", ...)`` decayed by its distance
    from ``(lat, lng)`` and its time offset from ``t``. Observations are
    ``{observed_at, lat, lng, twd_deg, confidence}``; one without a usable
    time is skipped, since its time decay is unknowable. Returns ``twd_deg``
    unchanged if nothing carries weight."""
    epoch = to_epoch(t)
    contributions = [(twd_deg, 1.0, own_weight)]
    for o in observations:
        observed_at = to_epoch(o["observed_at"])
        if epoch is None or observed_at is None:
            continue
        contributions.append((o["twd_deg"], 1.0, source_weight(
            "gps_tack",
            distance_km=haversine_km(lat, lng, o["lat"], o["lng"]),
            dt_seconds=epoch - observed_at,
            internal_confidence=o["confidence"],
        )))
    blended = weighted_wind_mean(contributions)
    return twd_deg if blended is None else blended[0]
