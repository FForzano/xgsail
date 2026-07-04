"""Wind endpoints (``/api/wind``): station catalog + cached observations.

Matrix: stations/observations are pub-readable; writes are system (fetch job)
or superadmin (station registration). The fetch itself is triggered on
``/api/system/wind/fetch`` by the wind-scheduler service.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_superadmin, verify_csrf
from ..schemas import WindStationWriteModel
from ._common import repos

router = APIRouter(prefix="/api/wind", tags=["wind"])


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
    if not body.provider or not body.external_station_id or not body.station_type:
        raise HTTPException(422, "provider, external_station_id and station_type are required")
    if repos.wind.get_by_provider_external(body.provider, body.external_station_id):
        raise HTTPException(409, "Station already registered")
    return repos.wind.create(body.model_dump(exclude_unset=True)).to_dict()


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
                      end: Optional[datetime] = None):
    _require_station(station_id)
    return [o.to_dict() for o in repos.wind.list_observations(station_id, start=start, end=end)]
