"""Raw wind gathering for a coordinate/time window.

Two distinct jobs, kept separate:

- ``gather_raw_wind`` — bundles *every* raw source relevant to a session's
  track/time window (real station in range, every Open-Meteo candidate
  model, any existing grid estimate) for the worker's wind-estimation
  algorithm to decide what to do with (see
  ``workers/process_upload/processing/wind_estimation.py``). No picking
  happens here anymore — that decision moved to the worker.
- ``live_snapshot`` — a quick, ephemeral "what's the wind here right now"
  for the WindCard/map display, unrelated to session analysis. Never
  blends: it walks the in-range real stations nearest-first and shows the
  first one with data, otherwise the first available Open-Meteo candidate,
  unblended. Nothing is persisted — this is *not* the rigorous
  per-session estimate.

Both go through ``_real_station_observations``, which returns up to
``MAX_REAL_STATIONS`` stations rather than only the nearest one.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from ..repositories import get_repos
from . import wind_estimates
from .wind_providers import open_meteo

if TYPE_CHECKING:
    from ..db.models.wind import WindObservationORM, WindStationORM

logger = logging.getLogger(__name__)

REAL_SENSOR_PROVIDERS = ("custom_device", "noaa_ndbc", "noaa_metar",
                         "cumulus_realtime", "cumulus_gauges_json")
REAL_SENSOR_RADIUS_KM = 50
MAX_REAL_STATIONS = 3


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
    """
    repos = get_repos()
    found = repos.wind.find_within(lat, lng, providers=list(REAL_SENSOR_PROVIDERS),
                                   max_km=REAL_SENSOR_RADIUS_KM, limit=MAX_REAL_STATIONS)
    out = []
    for station, distance_km in found:
        rows = repos.wind.list_observations(station.id, start=start, end=end, limit=500)
        if rows:
            out.append((station, distance_km, rows))
    return out


def gather_raw_wind(lat: float, lng: float, start: datetime, end: datetime,
                    gps_points: "Optional[list[tuple[float, float]]]" = None) -> dict:
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

    No selection happens here — see ``workers/process_upload/processing/
    wind_estimation.py`` for the algorithm that decides how to use this."""
    repos = get_repos()
    bundle: dict = {"real_stations": [], "model_candidates": {}, "grid_estimates": []}

    for station, distance_km, rows in _real_station_observations(lat, lng, start, end):
        # Every row carries its own station's position and distance from this
        # waypoint so the worker can distance-weight it (a station is a fixed
        # point offset from the track; the wind field differs across a bay).
        bundle["real_stations"].extend({
            "station_id": station.id, "provider": station.provider,
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

    return bundle


def live_snapshot(lat: float, lng: float, at: Optional[datetime] = None) -> Optional[dict]:
    """Quick display value for WindCard/map — not the per-session estimate.
    Walks the in-range real stations nearest-first and reports the first one
    with data near ``at``, so an offline nearest station falls back to the
    next one instead of dropping to a model; otherwise the first Open-Meteo
    candidate model with data. Never blends — this is one source's reading,
    attributed to it. Returns ``None`` if nothing is available."""
    at = at or datetime.now(timezone.utc)
    window = timedelta(hours=12)

    in_range = _real_station_observations(lat, lng, at - window, at + window)
    if in_range:
        station, _distance_km, rows = in_range[0]
        closest = min(rows, key=lambda o: abs((o.observed_at - at).total_seconds()))
        return {
            "provider": station.provider, "station_name": station.name,
            "lat": station.lat, "lng": station.lng,
            "observed_at": closest.observed_at, "twd_deg": closest.twd_deg,
            "tws_kts": closest.tws_kts, "gust_kts": closest.gust_kts,
        }

    external_id = f"{lat},{lng}"
    try:
        if at < datetime.now(timezone.utc):
            candidates = open_meteo.fetch_historical(external_id, at.date().isoformat(), at.date().isoformat())
        else:
            candidates = open_meteo.fetch_station(external_id)
    except Exception:
        logger.warning("open_meteo live snapshot failed for (%s, %s)", lat, lng, exc_info=True)
        candidates = {}

    for model in open_meteo.MODEL_CANDIDATES:
        rows = candidates.get(model)
        if not rows:
            continue
        closest = min(rows, key=lambda r: abs((r["observed_at"] - at).total_seconds()))
        return {
            "provider": "open_meteo", "model": model, "lat": lat, "lng": lng,
            "observed_at": closest["observed_at"], "twd_deg": closest["twd_deg"],
            "tws_kts": closest["tws_kts"], "gust_kts": closest["gust_kts"],
        }
    return None


__all__ = ["gather_raw_wind", "live_snapshot", "REAL_SENSOR_PROVIDERS",
           "REAL_SENSOR_RADIUS_KM", "MAX_REAL_STATIONS"]
