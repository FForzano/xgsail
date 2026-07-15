"""Internal ``system`` endpoints (``/api/system/*``) — hook-token bearer only.

The permission matrix's ``system`` actor: processing workers report status/
streams/stats here (workers stay DB-blind; the backend owns every DB write),
and the wind scheduler triggers the periodic fetch.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import AwareDatetime, BaseModel

from ..auth import require_system
from ..schemas import WindFetchModel
from ..services import ingestion, media, wind_estimate_refinement, wind_estimates
from ..services.wind_providers import PROVIDERS
from ._common import repos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])


class StreamPayload(BaseModel):
    sensor_type: str  # gps | imu | wind | pressure | heart_rate | estimated_position | estimated_motion | other
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


@router.post("/session-uploads/{upload_id}/analysis")
def upsert_session_analysis(upload_id: uuid.UUID, payload: dict, request: Request,
                            background_tasks: BackgroundTasks):
    """Persist the worker's analysis for an upload's session, fanning it out to
    its normalized homes: scalar aggregates → ``session_stats``, the empirical
    polar curve → ``polar_points``, discrete tacks/gybes → ``session_maneuvers``,
    legs → ``session_legs``, and the remaining matrices/series/distributions →
    ``session_analysis`` (JSON). The worker stays DB-blind: it posts the whole
    ``analysis.json`` dict and the backend owns the writes. Idempotent — every
    child set is replaced wholesale on re-runs."""
    require_system(request)
    upload = repos.ingest.get_upload(upload_id)
    if upload is None:
        raise HTTPException(404, "Upload not found")
    sid = upload.session_id
    now = datetime.now(timezone.utc)

    summary = payload.get("summary") or {}
    if summary:
        repos.sessions.upsert_stats(sid, {**summary, "computed_at": now})
    repos.polars.bulk_upsert(session_id=sid, source="empirical",
                             points=payload.get("polar_points") or [])
    repos.sessions.upsert_maneuvers(sid, payload.get("maneuvers") or [])
    repos.sessions.upsert_legs(sid, payload.get("legs") or [])
    # Estimated position/motion blobs (see processing/track.py) — registered
    # the same way any other sensor stream is, just sourced from analysis
    # instead of raw ingestion.
    streams = payload.get("streams") or []
    if streams:
        repos.ingest.upsert_streams(upload_id, streams)

    analysis_fields = {
        "correlations": payload.get("correlations"),
        "violin": payload.get("violin"),
        "maneuver_summary": payload.get("maneuver_summary"),
        "leg_comparison": payload.get("leg_comparison"),
        "sensor_stats": payload.get("session_stats"),
        "vmg_series": payload.get("vmg_series"),
        "polar_target": payload.get("polar_target"),
        "true_wind": payload.get("true_wind"),
        "computed_at": now,
    }
    # The worker already wrote the PNG straight to storage (it stays DB-blind)
    # — the backend just registers the resulting `images` row. Re-analyze
    # replaces it, so the old row (if any) is cleaned up rather than leaked.
    thumbnail_ref = payload.get("thumbnail_ref")
    if thumbnail_ref:
        thumbnail_image_id = media.register_processed_image(thumbnail_ref)
        if thumbnail_image_id is not None:
            previous = repos.sessions.get_analysis(sid)
            analysis_fields["thumbnail_image_id"] = thumbnail_image_id
            if previous and previous.thumbnail_image_id:
                # The worker always overwrites the same key (`{prefix}thumbnail.png`)
                # rather than rendering to a fresh one each time, so the "previous"
                # row usually has the SAME ref as the one we just registered —
                # deleting its blob would delete the file we just wrote.
                prev_image = repos.media.get_image(previous.thumbnail_image_id)
                same_key = prev_image is not None and prev_image.ref == thumbnail_ref
                media.delete_image(previous.thumbnail_image_id, deleted_by=None,
                                   keep_blob=same_key)
    repos.sessions.upsert_analysis(sid, analysis_fields)
    _apply_wind_refinements(sid, payload.get("wind_refinements") or [])

    # This session now has a track to show — (re)build the parent activity's
    # overlay thumbnail from every sibling session's most recently processed
    # prefix, not just this one (docs/er-project.md, activities note).
    #
    # Deferred as a background task (runs after this response is sent), not
    # called inline: this handler is itself invoked BY the worker's own
    # analysis callback, while that first worker invocation is still open —
    # the local dev Lambda RIE only runs one invocation at a time, so an
    # inline second dispatch here collides with the still-in-flight first one
    # ("ReserveFailed: AlreadyReserved") and crashes the emulator. Deferring
    # lets the worker's first invocation finish and free up before the
    # second (activity-thumbnail) one starts.
    if thumbnail_ref:
        session = repos.sessions.get(sid)
        if session is not None:
            background_tasks.add_task(_regenerate_activity_thumbnail, session.activity_id)
    return {"ok": True, "session_id": sid}


def _apply_wind_refinements(session_id: uuid.UUID, refinements: list) -> None:
    """Fold the worker's onboard-sensor wind observations into the
    ``wind_estimates`` grid — only ever called with real measurements (the
    worker emits these solely when it had an actual sensor, not a cached/
    estimated fallback). Combination logic is a pluggable skeleton, see
    ``services/wind_estimate_refinement.py`` — this just wires it to the
    grid cell/bucket the observation falls into."""
    for r in refinements:
        try:
            observed_at = r["observed_at"]
            if isinstance(observed_at, str):
                observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            cell_lat, cell_lng = wind_estimates.grid_cell(r["lat"], r["lng"])
            bucket = wind_estimates.time_bucket(observed_at)
            existing = repos.wind.get_estimate(cell_lat, cell_lng, bucket)
            new_estimate = wind_estimate_refinement.refine(
                existing.to_dict() if existing else None,
                {
                    "twd_deg": r.get("twd_deg"), "tws_kts": r.get("tws_kts"),
                    "gust_kts": r.get("gust_kts"), "type": r.get("source", "onboard_sensor"),
                    "session_id": str(session_id), "observed_at": r["observed_at"],
                },
            )
            repos.wind.upsert_estimate(cell_lat, cell_lng, bucket, new_estimate)
        except Exception:
            logger.warning("wind refinement failed for session %s: %r", session_id, r,
                           exc_info=True)


def _regenerate_activity_thumbnail(activity_id: uuid.UUID) -> None:
    # Even deferred to a background task, this still races the worker's own
    # still-unwinding first invocation: FastAPI runs the task right after the
    # response to the worker's callback POST is sent, which is well before
    # the local dev Lambda RIE actually marks that invocation done (it only
    # frees up once the worker process fully returns control to the
    # bootstrap loop). Firing the second invocation into that window hits
    # "ReserveFailed: AlreadyReserved" — and observed in practice, that
    # doesn't just fail this request, it panics the RIE process itself and
    # takes the whole worker container down (no auto-restart configured),
    # silently breaking all future processing. A short delay here is enough
    # slack for the first invocation to actually finish first.
    time.sleep(3)
    prefixes = ingestion.activity_thumbnail_prefixes(activity_id)
    if prefixes:
        ingestion.dispatch_activity_thumbnail(ingestion.bucket_name(), activity_id, prefixes)


class ActivityThumbnailPayload(BaseModel):
    thumbnail_ref: str


@router.post("/activities/{activity_id}/thumbnail")
def upsert_activity_thumbnail(activity_id: uuid.UUID, payload: ActivityThumbnailPayload,
                              request: Request):
    """Register the worker-composited overlay PNG (see
    ``dispatch_activity_thumbnail``) as the activity's thumbnail, cleaning up
    the previous one — same registration pattern as the session thumbnail
    above, just parented to ``activities`` instead of ``session_analysis``."""
    require_system(request)
    activity = repos.activities.get(activity_id)
    if activity is None:
        raise HTTPException(404, "Activity not found")
    thumbnail_image_id = media.register_processed_image(payload.thumbnail_ref)
    if thumbnail_image_id is None:
        raise HTTPException(409, "Thumbnail image not found in storage")
    previous_id = activity.thumbnail_image_id
    repos.activities.update(activity_id, {"thumbnail_image_id": thumbnail_image_id})
    if previous_id:
        # Same reused-key hazard as the session thumbnail above — the worker
        # always writes to `activities/{id}/thumbnail.png`, so the previous
        # row's ref is usually identical to the one we just registered.
        prev_image = repos.media.get_image(previous_id)
        same_key = prev_image is not None and prev_image.ref == payload.thumbnail_ref
        media.delete_image(previous_id, deleted_by=None, keep_blob=same_key)
    return {"ok": True, "activity_id": activity_id}


class ManeuverComputedPayload(BaseModel):
    duration_sec: float
    speed_loss_kts: float
    speed_before_kts: float
    speed_min_kts: float
    speed_after_kts: float
    recovery_time_sec: float
    heading_change_deg: float
    distance_lost_m: Optional[float] = None
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    features: Optional[dict] = None


@router.post("/maneuvers/{maneuver_id}/computed")
def maneuver_computed(maneuver_id: uuid.UUID, payload: ManeuverComputedPayload, request: Request):
    """Worker callback after computing a manually-added maneuver's stats
    (see ``services/ingestion.dispatch_maneuver_compute`` and
    ``workers/process_upload/handler.py::process_compute_maneuver``). Fills
    the pending row's stat columns and clears ``pending`` — see
    ``repos.sessions.fill_manual_maneuver``."""
    require_system(request)
    updated = repos.sessions.fill_manual_maneuver(maneuver_id, payload.model_dump())
    if updated is None:
        raise HTTPException(404, "Maneuver not found")
    return {"ok": True}


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
                rows = fetch(station)
                inserted += repos.wind.upsert_observations(station.id, rows)
            except Exception as exc:  # one bad station must not stop the sweep
                errors.append(f"{provider}/{station.external_station_id}: {exc}")
    return {"stations": stations_hit, "inserted": inserted, "errors": errors}
