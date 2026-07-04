"""Internal ``system`` endpoints (``/api/system/*``) — hook-token bearer only.

The permission matrix's ``system`` actor: processing workers report status/
streams/stats here (workers stay DB-blind; the backend owns every DB write),
and the wind scheduler triggers the periodic fetch.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel

from ..auth import require_system
from ..schemas import WindFetchModel
from ..services.wind_providers import PROVIDERS
from ._common import repos

router = APIRouter(prefix="/api/system", tags=["system"])


class StreamPayload(BaseModel):
    sensor_type: str  # gps | imu | wind | pressure | heart_rate | other
    data_ref: str
    sample_rate_hz: Optional[float] = None
    row_count: Optional[int] = None


class IngestCompletePayload(BaseModel):
    session_upload_id: uuid.UUID
    status: str  # processed | failed
    error: Optional[str] = None
    start_time: Optional[AwareDatetime] = None
    end_time: Optional[AwareDatetime] = None
    streams: list[StreamPayload] = []


class UploadStatusPayload(BaseModel):
    status: str  # pending | processing | processed | failed
    error: Optional[str] = None


class SessionStatsPayload(BaseModel):
    distance_m: Optional[float] = None
    avg_speed_kts: Optional[float] = None
    max_speed_kts: Optional[float] = None
    duration_s: Optional[int] = None
    avg_polar_pct: Optional[float] = None
    max_polar_pct: Optional[float] = None


@router.post("/ingest/complete")
def ingest_complete(payload: IngestCompletePayload, request: Request):
    """Worker callback after processing one file of an upload bundle.

    Bundle files (nav/imu/wind/pressure) arrive as independent storage events,
    so several callbacks per upload are normal: streams are upserted by
    sensor_type, the session window only widens, and a ``failed`` never
    downgrades an upload that already has processed data. Idempotent on
    retries."""
    require_system(request)
    upload = repos.ingest.get_upload(payload.session_upload_id)
    if upload is None:
        raise HTTPException(404, "Upload not found")

    if payload.streams:
        repos.ingest.upsert_streams(upload.id, [s.model_dump() for s in payload.streams])

    if payload.status == "processed":
        repos.ingest.set_upload_status(upload.id, "processed")
    elif payload.status == "failed" and upload.status != "processed":
        repos.ingest.set_upload_status(upload.id, "failed")

    if payload.start_time or payload.end_time:
        repos.sessions.extend_window(upload.session_id, payload.start_time, payload.end_time)
    session_status = repos.sessions.rollup_status(upload.session_id)
    return {"ok": True, "session_status": session_status}


@router.post("/session-uploads/{upload_id}/status")
def set_upload_status(upload_id: uuid.UUID, payload: UploadStatusPayload, request: Request):
    require_system(request)
    upload = repos.ingest.get_upload(upload_id)
    if upload is None:
        raise HTTPException(404, "Upload not found")
    repos.ingest.set_upload_status(upload_id, payload.status)
    repos.sessions.rollup_status(upload.session_id)
    return {"ok": True}


@router.post("/sessions/{session_id}/stats")
def upsert_session_stats(session_id: uuid.UUID, payload: SessionStatsPayload,
                         request: Request):
    require_system(request)
    if repos.sessions.get(session_id) is None:
        raise HTTPException(404, "Session not found")
    data = payload.model_dump(exclude_unset=True)
    data["computed_at"] = datetime.now(timezone.utc)
    return repos.sessions.upsert_stats(session_id, data).to_dict()


@router.post("/wind/fetch")
def wind_fetch(payload: WindFetchModel, request: Request):
    """Periodic fetch trigger (wind-scheduler service). Iterates the DB
    stations of the requested provider(s); the unique (station, observed_at)
    constraint makes re-runs idempotent."""
    require_system(request)
    providers = [payload.provider] if payload.provider else list(PROVIDERS)
    stations_hit = 0
    inserted = 0
    errors: list[str] = []
    for provider in providers:
        fetch = PROVIDERS.get(provider)
        if fetch is None:
            errors.append(f"unknown provider: {provider}")
            continue
        for station in repos.wind.list(provider=provider):
            stations_hit += 1
            try:
                rows = fetch(station.external_station_id)
                inserted += repos.wind.upsert_observations(station.id, rows)
            except Exception as exc:  # one bad station must not stop the sweep
                errors.append(f"{provider}/{station.external_station_id}: {exc}")
    return {"stations": stations_hit, "inserted": inserted, "errors": errors}
