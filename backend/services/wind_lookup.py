"""Raw wind gathering for a coordinate/time window.

Two distinct jobs, kept separate:

- ``gather_raw_wind`` — bundles *every* raw source relevant to a session's
  track/time window (real station in range, every Open-Meteo candidate
  model, any existing grid estimate) for the worker's wind-estimation
  algorithm to decide what to do with (see
  ``workers/process_upload/processing/wind_estimation.py``). No picking
  happens here anymore — that decision moved to the worker.
- ``live_snapshot`` — a quick "what's the wind here right now" for the
  WindCard/map display, unrelated to session analysis (nothing is
  persisted). It fuses the same waypoint bundle the same way the analysis
  estimate does — ``xgsail_windfusion.fuse_waypoint`` then
  ``blend_direction`` toward nearby tack/gybe observations — so the live
  badge and the session's own estimate never disagree about "the wind
  here". See its own docstring for how it handles the point directly
  under "now", where a real station's newest reading is usually a few
  minutes stale.

Both go through ``_real_station_observations``, which returns up to
``MAX_REAL_STATIONS`` stations rather than only the nearest one.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from xgsail_windfusion import (
    MODEL_SOURCE_TYPE,
    blend_direction,
    fuse_waypoint,
    haversine_km,
    source_weight,
    station_groups,
    to_epoch,
)

from ..repositories import get_repos
from . import wind_estimates, wind_quality
from .wind_providers import open_meteo

if TYPE_CHECKING:
    from ..db.models.wind import WindObservationORM, WindStationORM

logger = logging.getLogger(__name__)

REAL_SENSOR_PROVIDERS = ("custom_device", "noaa_ndbc", "noaa_metar",
                         "cumulus_realtime", "cumulus_gauges_json")
REAL_SENSOR_RADIUS_KM = 50
MAX_REAL_STATIONS = 3

# The fault check (``wind_quality``) needs a dense enough sample to reach a
# verdict, and a short session would not provide one on its own — a 20-minute
# outing is four readings from a 5-minute feed. So the observations are
# fetched over a window padded by this much on each side and the verdict is
# taken on all of them, while only the rows actually inside [start, end] are
# handed on. One wider query, not a second one: this runs per waypoint.
FAULT_CHECK_PAD = timedelta(hours=3)

# Maneuver-derived wind observations from *other* sessions (see
# ``services/track_wind.py``): how far from a waypoint, and how far outside
# the session's own window, one still counts as relevant. The ``gps_tack``
# weight decays with a 2 km e-folding distance, so past ~3 km an observation
# weighs under 22% — not worth a neighbour's wind cache, nor (same constant,
# ``services/wind_auto_refresh.py``) a neighbour's re-analysis.
TRACK_OBS_RADIUS_KM = 3.0
TRACK_OBS_TIME_PAD = timedelta(minutes=30)


def _real_station_observations(lat: float, lng: float, start: datetime, end: datetime
                               ) -> "list[tuple[WindStationORM, float, list[WindObservationORM]]]":
    """Up to ``MAX_REAL_STATIONS`` real stations within
    ``REAL_SENSOR_RADIUS_KM``, nearest first, as
    ``(station, distance_km, rows)`` — each with its own cached
    observations for [start, end].

    A station with nothing cached for the window is simply left out; there
    is deliberately no special case for "the nearest one is offline".
    Relevance is handled downstream by distance weighting, and a hard
    nearest-only pick would also make the chosen station flip
    discontinuously from waypoint to waypoint along a long track.

    A station whose readings look mechanically faulty (a dead vane repeating
    one direction, a dead anemometer repeating one speed — see
    ``wind_quality``) is left out the same way. That verdict is taken on a
    window padded by ``FAULT_CHECK_PAD``, so a short session still has enough
    readings behind it to reach one, while the rows returned are only those
    inside the caller's own window. The check lives here, in the
    one helper both callers share, so a broken sensor is kept out of the
    fused wind *and* of the arrow the map draws. It excludes the station
    wholesale rather than nulling the bad field: ``weighted_wind_mean``
    averages vectors, and a vector needs both a direction and a speed.
    """
    repos = get_repos()
    found = repos.wind.find_within(lat, lng, providers=list(REAL_SENSOR_PROVIDERS),
                                   max_km=REAL_SENSOR_RADIUS_KM, limit=MAX_REAL_STATIONS)
    out = []
    for station, distance_km in found:
        padded = repos.wind.list_observations(station.id, start=start - FAULT_CHECK_PAD,
                                              end=end + FAULT_CHECK_PAD, limit=500)
        rows = [o for o in padded if start <= o.observed_at <= end]
        if not rows:
            continue
        fault = wind_quality.station_readings_are_faulty(padded)
        if fault:
            logger.warning("wind station %s (%s) excluded: %s", station.id, station.name, fault)
            continue
        out.append((station, distance_km, rows))
    return out


def gather_raw_wind(lat: float, lng: float, start: datetime, end: datetime,
                    gps_points: "Optional[list[tuple[float, float]]]" = None, *,
                    session_id: Optional[uuid.UUID] = None) -> dict:
    """Bundle every raw wind source for a coordinate/time window:

    - ``real_stations``: cached observations from every real station in
      range (up to ``MAX_REAL_STATIONS``, nearest first), flattened into
      one row list — the worker regroups them by ``station_id`` and
      distance-weights them. Empty if no station in range has data for
      this window.
    - ``model_candidates``: ``{model_name: rows}`` from every Open-Meteo
      model that covers this point — archive endpoint if ``end`` is in the
      past (the common case: sessions already happened), forecast endpoint
      otherwise.
    - ``grid_estimates``: any ``wind_estimates`` rows already on file for
      this cell within the window — reusable/refinable knowledge from
      earlier sessions at the same place.
    - ``track_observations``: wind directions inferred from the tacks/gybes
      of *other* sessions (never ``session_id``'s own — it would be fed its
      own estimate back) within ``TRACK_OBS_RADIUS_KM`` and ``[start, end]``
      padded by ``TRACK_OBS_TIME_PAD``. Rows carry no session, user or boat:
      another crew's whereabouts are not this session's to know.

    No selection happens here — see ``workers/process_upload/processing/
    wind_estimation.py`` for the algorithm that decides how to use this."""
    repos = get_repos()
    bundle: dict = {"real_stations": [], "model_candidates": {}, "grid_estimates": [],
                    "track_observations": []}

    for station, distance_km, rows in _real_station_observations(lat, lng, start, end):
        # Every row carries its own station's position and distance from this
        # waypoint so the worker can distance-weight it (a station is a fixed
        # point offset from the track; the wind field differs across a bay).
        bundle["real_stations"].extend({
            "station_id": station.id, "provider": station.provider,
            "station_name": station.name,
            "station_lat": station.lat, "station_lng": station.lng,
            "distance_km": round(distance_km, 3),
            "observed_at": o.observed_at, "twd_deg": o.twd_deg,
            "tws_kts": o.tws_kts, "gust_kts": o.gust_kts,
        } for o in rows)

    external_id = f"{lat},{lng}"
    try:
        if end < datetime.now(timezone.utc):
            bundle["model_candidates"] = open_meteo.fetch_historical(
                external_id, start.date().isoformat(), end.date().isoformat(), gps_points=gps_points)
        else:
            bundle["model_candidates"] = open_meteo.fetch_station(external_id, gps_points=gps_points)
    except Exception:
        logger.warning("open_meteo fetch failed for (%s, %s)", lat, lng, exc_info=True)

    cell = wind_estimates.grid_cell(lat, lng)
    bundle["grid_estimates"] = [{
        "grid_lat": e.grid_lat, "grid_lng": e.grid_lng, "time_bucket": e.time_bucket,
        "twd_deg": e.twd_deg, "tws_kts": e.tws_kts, "gust_kts": e.gust_kts,
        "confidence": e.confidence,
    } for e in repos.wind.list_estimates_for_cells([cell], start, end)]

    bundle["track_observations"] = [{
        "id": str(o.id), "observed_at": o.observed_at.isoformat(),
        "lat": o.lat, "lng": o.lng, "twd_deg": o.twd_deg,
        "confidence": o.confidence, "kind": o.kind,
    } for o in repos.wind.list_track_observations_near(
        lat, lng, TRACK_OBS_RADIUS_KM, start - TRACK_OBS_TIME_PAD, end + TRACK_OBS_TIME_PAD,
        exclude_session_id=session_id,
    )]

    return bundle


# Real stations report every ~10-60 min, Open-Meteo models hourly — a window
# this wide on each side of ``at`` reliably brackets it for interpolation
# (and gives ``_real_station_observations``'s fault check, itself padded by
# another ``FAULT_CHECK_PAD``, a real sample to judge). Unlike the old
# nearest-station walk, there's no need for this to reach out 12h: the "now"
# edge case (a station's newest reading trailing behind ``at``) is handled
# below via ``LIVE_HOLD_LATEST``, not by widening the query.
LIVE_SNAPSHOT_WINDOW = timedelta(hours=3)

# How long a source may lag behind ``at`` and still count, decayed by the
# gap — see ``xgsail_windfusion.fuse_sources``'s ``hold_latest_seconds``. A
# live query is overwhelmingly "what's the wind right now": without this, a
# station reporting every 30-60 min would drop out of *every* live snapshot
# taken between two readings, leaving only the (less trusted) forecast
# models. Comfortably longer than a station's own reporting interval, safely
# inside ``LIVE_SNAPSHOT_WINDOW`` so the held reading was already fetched.
LIVE_HOLD_LATEST = timedelta(hours=2)


def live_snapshot(lat: float, lng: float, at: Optional[datetime] = None) -> Optional[dict]:
    """Quick display value for WindCard/map, the navigation overlay and the
    explorer/Registra map badge — fused the same way the session-analysis
    estimate is, so the live number and the per-session one never disagree
    about "the wind here": every raw source in range
    (``gather_raw_wind``) fused with ``xgsail_windfusion.fuse_waypoint``,
    then pulled toward nearby tack/gybe observations with
    ``blend_direction`` — the two-step estimate ``workers/process_upload/
    processing/wind_estimation.py`` + ``tack_wind.py`` apply per-session.

    ``at`` defaults to now, the case a real station is least likely to
    have a reading for: its own last observation typically trails "now" by
    however long its reporting interval is, and a source never
    extrapolates past its own span. ``LIVE_HOLD_LATEST`` lets a source hold
    its last reading across that gap, weight decayed accordingly, rather
    than silently dropping to forecast-model-only every time nobody has
    reported in the last few seconds.

    Returns ``None`` if no source covers ``at`` at all (station, model,
    grid estimate) — same "nothing to report" case ``fuse_waypoint``
    itself returns ``None`` for."""
    at = at or datetime.now(timezone.utc)
    bundle = gather_raw_wind(lat, lng, at - LIVE_SNAPSHOT_WINDOW, at + LIVE_SNAPSHOT_WINDOW,
                             session_id=None)
    waypoint = {"lat": lat, "lng": lng, **bundle}
    fused = fuse_waypoint(waypoint, at, hold_latest_seconds=LIVE_HOLD_LATEST.total_seconds())
    if fused is None:
        return None

    at_epoch = to_epoch(at)
    observations = bundle["track_observations"]
    twd = blend_direction(fused.twd_deg, fused.confidence, lat, lng, at, observations)

    tack_weight = 0.0
    for o in observations:
        observed_at = to_epoch(o.get("observed_at"))
        if at_epoch is None or observed_at is None:
            continue
        tack_weight += source_weight(
            "gps_tack",
            distance_km=haversine_km(lat, lng, o["lat"], o["lng"]),
            dt_seconds=at_epoch - observed_at,
            internal_confidence=o["confidence"],
        )

    total_weight = fused.confidence + tack_weight
    sources = [
        {"type": source_type, "name": name, "weight_share": round(weight / total_weight, 2)}
        for source_type, name, weight in fused.contributions
    ] if total_weight > 0.0 else []
    if tack_weight > 0.0 and total_weight > 0.0:
        sources.append({"type": "gps_tack", "name": None,
                        "weight_share": round(tack_weight / total_weight, 2)})
    sources.sort(key=lambda s: s["weight_share"], reverse=True)

    return {
        "provider": "fusion", "station_name": None, "model": None,
        "lat": lat, "lng": lng,
        "observed_at": at.isoformat(),
        "twd_deg": round(twd, 1), "tws_kts": round(fused.tws_kts, 1),
        "gust_kts": round(fused.gust_kts, 1) if fused.gust_kts is not None else None,
        "confidence": round(total_weight, 3),
        "latest_observed_at": _latest_contributing_reading(bundle, fused.contributions),
        "sources": sources,
    }


def _latest_contributing_reading(bundle: dict, contributions) -> Optional[str]:
    """ISO timestamp of the newest raw reading among the real stations/models
    that actually contributed to a fused estimate (``fused.contributions``)
    — i.e. excluding a source that was in range but didn't cover ``at`` and
    so was already dropped by ``fuse_sources``. ``None`` if nothing
    contributing carries a usable timestamp (e.g. only a grid estimate did)."""
    contributing = {(source_type, name) for source_type, name, _weight in contributions}
    latest_epoch: Optional[float] = None

    for _distance_km, rows in station_groups(bundle["real_stations"]):
        first = rows[0]
        name = first.get("station_name") or first.get("station_id")
        if ("real_station", name) not in contributing:
            continue
        for r in rows:
            epoch = to_epoch(r.get("observed_at"))
            if epoch is not None and (latest_epoch is None or epoch > latest_epoch):
                latest_epoch = epoch

    for model, rows in (bundle.get("model_candidates") or {}).items():
        source_type = MODEL_SOURCE_TYPE.get(model, "model_global")
        if (source_type, model) not in contributing:
            continue
        for r in rows or []:
            epoch = to_epoch(r.get("observed_at"))
            if epoch is not None and (latest_epoch is None or epoch > latest_epoch):
                latest_epoch = epoch

    if latest_epoch is None:
        return None
    return datetime.fromtimestamp(latest_epoch, tz=timezone.utc).isoformat()


__all__ = ["gather_raw_wind", "live_snapshot", "REAL_SENSOR_PROVIDERS",
           "REAL_SENSOR_RADIUS_KM", "MAX_REAL_STATIONS", "TRACK_OBS_RADIUS_KM",
           "LIVE_SNAPSHOT_WINDOW", "LIVE_HOLD_LATEST"]
