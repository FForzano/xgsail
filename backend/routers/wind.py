"""Wind endpoints (``/api/wind``): real-station catalog + cached
observations, plus a live snapshot for the WindCard/map display.

Matrix: stations/observations are pub-readable; writes are system (fetch
job) or superadmin (station registration). ``/nearest`` is any authenticated
user, and is a quick display value only (see ``services/wind_lookup.
live_snapshot``) — it is *not* the rigorous per-session wind estimate used
by analysis (that lives with the session's own processed data, computed by
the worker). The periodic fetch for real stations is triggered on
``/api/system/wind/fetch`` by the wind-scheduler service.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from ..auth import require_superadmin, require_user, verify_csrf
from ..schemas import WindStationWriteModel
from ..services import wind_lookup
from ..services.wind_providers import URL_BASED_PROVIDERS
from ._common import repos

router = APIRouter(prefix="/api/wind", tags=["wind"])

OBSERVATIONS_DEFAULT_WINDOW_HOURS = 72
OBSERVATIONS_MAX_LIMIT = 1000


def _require_station(station_id: uuid.UUID):
    station = repos.wind.get(station_id)
    if station is None:
        raise HTTPException(404, "Wind station not found")
    return station


@router.get("/stations")
def list_stations(provider: Optional[str] = None):
    return [s.to_dict() for s in repos.wind.list(provider=provider)]


@router.get("/stations/{station_id}")
def get_station(station_id: uuid.UUID):
    return _require_station(station_id).to_dict()


@router.post("/stations")
def create_station(body: WindStationWriteModel, request: Request):
    verify_csrf(request)
    require_superadmin(request)
    if not body.provider or not body.station_type or not body.external_station_id:
        raise HTTPException(422, "provider, station_type and external_station_id are required")
    if body.provider in URL_BASED_PROVIDERS and not body.source_url:
        raise HTTPException(422, f"source_url is required for provider={body.provider}")
    data = body.model_dump(exclude_unset=True)
    if repos.wind.get_by_provider_external(body.provider, data["external_station_id"]):
        raise HTTPException(409, "Station already registered")
    return repos.wind.create(data).to_dict()


@router.patch("/stations/{station_id}")
def update_station(station_id: uuid.UUID, body: WindStationWriteModel, request: Request):
    verify_csrf(request)
    require_superadmin(request)
    _require_station(station_id)
    return repos.wind.update(station_id, body.model_dump(exclude_unset=True)).to_dict()


@router.delete("/stations/{station_id}")
def delete_station(station_id: uuid.UUID, request: Request):
    verify_csrf(request)
    require_superadmin(request)
    if not repos.wind.delete(station_id):
        raise HTTPException(404, "Wind station not found")
    return {"ok": True}


@router.get("/stations/{station_id}/observations")
def list_observations(station_id: uuid.UUID,
                      start: Optional[datetime] = None,
                      end: Optional[datetime] = None,
                      limit: int = Query(200, le=OBSERVATIONS_MAX_LIMIT, gt=0),
                      offset: int = Query(0, ge=0)):
    """Newest-first, paginated. The cache grows without bound (idempotent
    upsert on every scheduler tick) — defaults to the last 72h when no
    explicit range is given, rather than dumping the whole history."""
    station = _require_station(station_id)
    if start is None and end is None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=OBSERVATIONS_DEFAULT_WINDOW_HOURS)
    rows = repos.wind.list_observations(station.id, start=start, end=end,
                                        limit=limit, offset=offset)
    return [o.to_dict() for o in rows]


@router.get("/nearest")
def nearest_wind(lat: float, lng: float, request: Request, at: Optional[datetime] = None):
    """Quick live snapshot for a coordinate/time — WindCard/map display
    only. Prefers a real station in range with data near ``at``; otherwise
    an unblended Open-Meteo candidate model. Nothing is created/persisted —
    see ``services/wind_lookup.live_snapshot``."""
    require_user(request)
    snapshot = wind_lookup.live_snapshot(lat, lng, at)
    if snapshot is None:
        raise HTTPException(404, "No wind data available near this point")
    return snapshot
