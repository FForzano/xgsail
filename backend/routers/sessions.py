"""Session endpoints (``/api/sessions``).

A session is one boat's participation in an activity; visibility follows the
parent activity, with crew and boat members always able to see their own
sessions (``session_visible_to``). Data ingestion happens through the device
API / imports — here it's CRUD, crew, media, streams and stats reads.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from ..auth import can_edit_activity, current_user, require_user, session_visible_to, verify_csrf
from ..schemas import (
    ManeuverCorrectionModel,
    ManeuverCreateModel,
    ManeuverRejectionModel,
    SessionAttachModel,
    SessionCrewModel,
    SessionTrimModel,
    SessionWriteModel,
)
from ..services import gpx, ingestion, media
from ._common import blob, load_json_or_404, repos, with_user

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)


def _require_session(session_id: uuid.UUID):
    session = repos.sessions.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    return session


def _require_visible(session_id: uuid.UUID, user):
    session = _require_session(session_id)
    if not session_visible_to(session, user):
        raise HTTPException(404, "Session not found")
    return session


def _can_edit(session, user) -> bool:
    """Boat owner/admin or the parent activity's creator (matrix)."""
    if user is None:
        return False
    if user.is_superadmin:
        return True
    if repos.boats.is_member(session.boat_id, user.id, roles=["owner", "admin"]):
        return True
    activity = repos.activities.get(session.activity_id)
    return activity is not None and activity.created_by == user.id


def _is_crew_or_manager(session, user) -> bool:
    if user is None:
        return False
    return (user.is_superadmin
            or repos.sessions.is_crew(session.id, user.id)
            or repos.boats.is_member(session.boat_id, user.id, roles=["owner", "admin"]))


@router.get("")
def list_sessions(request: Request, activity_id: Optional[uuid.UUID] = None,
                  boat_id: Optional[uuid.UUID] = None, mine: bool = False):
    user = current_user(request)
    if mine:
        if user is None:
            raise HTTPException(401, "Authentication required")
        # Boat membership / crew implies visibility — no extra filter needed.
        return [media.session_thumbnail_payload(s) for s in repos.sessions.list_for_user(user.id)]
    sessions = repos.sessions.list(activity_id=activity_id, boat_id=boat_id)
    return [media.session_thumbnail_payload(s) for s in sessions if session_visible_to(s, user)]


@router.get("/{session_id}")
def get_session(session_id: uuid.UUID, request: Request):
    return _require_visible(session_id, current_user(request)).to_dict()


@router.post("")
def create_session(body: SessionWriteModel, request: Request):
    """Manual creation by the activity creator (ingestion flows create their
    own sessions — see device API / imports)."""
    verify_csrf(request)
    user = require_user(request)
    if body.activity_id is None or body.boat_id is None:
        raise HTTPException(422, "activity_id and boat_id are required")
    activity = repos.activities.get(body.activity_id)
    if activity is None:
        raise HTTPException(404, "Activity not found")
    if activity.created_by != user.id and not user.is_superadmin:
        raise HTTPException(403, "Only the activity creator adds sessions")
    if repos.boats.get(body.boat_id) is None:
        raise HTTPException(404, "Boat not found")
    return repos.sessions.create(body.model_dump(exclude_unset=True)).to_dict()


@router.patch("/{session_id}")
def update_session(session_id: uuid.UUID, body: SessionWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    changes = body.model_dump(exclude_unset=True)
    changes.pop("activity_id", None)  # re-parenting is a race/compute concern
    changes.pop("boat_id", None)
    return repos.sessions.update(session_id, changes).to_dict()


@router.post("/{session_id}/attach-to-activity")
def attach_to_activity(session_id: uuid.UUID, body: SessionAttachModel, request: Request):
    """Move a standalone recording (a private, auto-created ``solo`` activity
    wrapping exactly this one session — see
    ``services.ingestion.find_or_create_session``) into an existing
    activity/regatta. Deliberately narrower than a general "re-parent this
    session" endpoint (``PATCH /sessions/{id}`` strips ``activity_id`` for
    exactly that reason — see ``update_session`` above): only allowed while
    the session's current activity is still a lone standalone wrapper, so a
    session that's already part of a real multi-session activity or race
    can't be silently moved elsewhere. If the target activity is a
    ``planned`` announcement, this is also the point where it flips to
    ``completed`` — the first recording proves the event actually happened."""
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    current_activity = repos.activities.get(session.activity_id)
    if (current_activity is None or current_activity.type != "solo"
            or len(repos.sessions.list(activity_id=current_activity.id)) != 1):
        raise HTTPException(409, "Only a standalone recording can be reassigned")
    target_activity = repos.activities.get(body.activity_id)
    if target_activity is None:
        raise HTTPException(404, "Activity not found")
    if not can_edit_activity(target_activity, user):
        raise HTTPException(403, "Not allowed to attach to this activity")
    updated = repos.sessions.update(session_id, {"activity_id": body.activity_id})
    repos.activities.delete(current_activity.id)
    if target_activity.status == "planned":
        # First recording lands on an announced event — it has actually
        # happened now, so it moves out of "upcoming" into "past".
        repos.activities.update(target_activity.id, {"status": "completed"})
    return updated.to_dict()


@router.delete("/{session_id}")
def delete_session(session_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    # Delete is stricter than edit: boat OWNER or activity creator (matrix).
    activity = repos.activities.get(session.activity_id)
    allowed = (user.is_superadmin
               or repos.boats.is_member(session.boat_id, user.id, roles=["owner"])
               or (activity is not None and activity.created_by == user.id))
    if not allowed:
        raise HTTPException(403, "Boat owner or activity creator required")
    repos.sessions.delete(session_id)
    return {"ok": True}


def _latest_upload_or_404(session_id: uuid.UUID):
    uploads = repos.ingest.list_uploads(session_id=session_id)
    if not uploads:
        raise HTTPException(404, "No processed data for this session")
    return max(uploads, key=lambda u: u.uploaded_at)


def _start_reanalysis_job(upload) -> None:
    """Guard against overlapping reanalyze/wind-refresh runs on the same
    upload — both jobs touch ``wind_cache.json``/``analysis.json`` and
    running two at once would race on those blobs."""
    if upload.reanalysis_status == "running":
        raise HTTPException(409, "A reanalysis is already in progress for this session")
    repos.ingest.set_reanalysis_status(upload.id, "running", error=None)


def _run_reanalyze(upload_id: uuid.UUID, prefix: str, trim_start: Optional[float] = None,
                   trim_end: Optional[float] = None) -> None:
    try:
        ingestion.dispatch_analysis(ingestion.bucket_name(), prefix,
                                    trim_start=trim_start, trim_end=trim_end)
        repos.ingest.set_reanalysis_status(upload_id, None)
    except Exception as exc:
        logger.warning("reanalyze job failed for upload %s", upload_id, exc_info=True)
        repos.ingest.set_reanalysis_status(upload_id, "failed", str(exc))


def _run_wind_refresh(session_id: uuid.UUID, upload_id: uuid.UUID) -> None:
    try:
        ingestion.refresh_wind_cache(session_id)
        repos.ingest.set_reanalysis_status(upload_id, None)
    except Exception as exc:
        logger.warning("wind refresh job failed for session %s", session_id, exc_info=True)
        repos.ingest.set_reanalysis_status(upload_id, "failed", str(exc))


@router.post("/{session_id}/reanalyze", status_code=202)
def reanalyze_session(session_id: uuid.UUID, request: Request, background_tasks: BackgroundTasks):
    """Re-run the processing pipeline (maneuvers/legs/polar/VMG/…) on the
    session's already-processed data — e.g. after a detection-logic change,
    without re-importing. Same edit-level permission as PATCH; re-dispatches
    to the most recently uploaded processed prefix, which already has
    gps.json/wind_cache.json in place from the original import.

    Runs in the background (worker dispatch can take up to
    ``WORKER_TIMEOUT_SEC``) — the response only confirms the job started;
    poll ``GET .../reanalysis-status`` for completion."""
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    upload = _latest_upload_or_404(session_id)
    _start_reanalysis_job(upload)
    prefix = ingestion.processed_prefix(upload.id)
    background_tasks.add_task(_run_reanalyze, upload.id, prefix,
                              session.trim_start_time, session.trim_end_time)
    return {"ok": True, "session_upload_id": upload.id, "status": "running"}


@router.patch("/{session_id}/trim", status_code=202)
def set_session_trim(session_id: uuid.UUID, body: SessionTrimModel, request: Request,
                     background_tasks: BackgroundTasks):
    """Set (or clear, passing both as null) the session's reversible
    track-trim bounds and immediately re-run analysis with them applied —
    same edit-level permission and background-job plumbing as ``reanalyze``.
    Raw ``gps.json`` is never touched; the worker just slices the parsed
    track to this window before running the pipeline (see
    ``workers/process_upload/analyzer.py::_slice_by_time``), so the trim is
    always adjustable later, not a destructive crop."""
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    if (body.trim_start_time is not None and body.trim_end_time is not None
            and body.trim_end_time <= body.trim_start_time):
        raise HTTPException(422, "trim_end_time must be after trim_start_time")
    session = repos.sessions.update(session_id, body.model_dump())
    upload = _latest_upload_or_404(session_id)
    _start_reanalysis_job(upload)
    prefix = ingestion.processed_prefix(upload.id)
    background_tasks.add_task(_run_reanalyze, upload.id, prefix,
                              session.trim_start_time, session.trim_end_time)
    return {"ok": True, "session_upload_id": upload.id, "status": "running"}


@router.post("/{session_id}/wind/refresh", status_code=202)
def refresh_session_wind(session_id: uuid.UUID, request: Request, background_tasks: BackgroundTasks):
    """Recompute the session's ``wind_cache.json`` (multi-waypoint sampling,
    tighter Open-Meteo grid — see ``services/ingestion.refresh_wind_cache``)
    and re-run analysis. For sessions ingested before those improvements
    landed; new sessions get them automatically. Same edit-level permission
    as PATCH/reanalyze.

    Runs in the background — the multi-source wind fetch plus worker
    dispatch can take a while; poll ``GET .../reanalysis-status``."""
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    upload = _latest_upload_or_404(session_id)
    _start_reanalysis_job(upload)
    background_tasks.add_task(_run_wind_refresh, session_id, upload.id)
    return {"ok": True, "session_upload_id": upload.id, "status": "running"}


@router.get("/{session_id}/reanalysis-status")
def get_reanalysis_status(session_id: uuid.UUID, request: Request):
    """Poll target for the reanalyze/wind-refresh background job — see
    ``_start_reanalysis_job``. ``status`` is ``null`` when idle (no job
    running, or the last one finished successfully)."""
    session = _require_visible(session_id, current_user(request))
    uploads = repos.ingest.list_uploads(session_id=session.id)
    if not uploads:
        return {"status": None, "error": None}
    upload = max(uploads, key=lambda u: u.uploaded_at)
    return {"status": upload.reanalysis_status, "error": upload.reanalysis_error}


# --- streams / stats / analysis --------------------------------------------------

@router.get("/{session_id}/streams")
def list_streams(session_id: uuid.UUID, request: Request):
    user = current_user(request)
    _require_visible(session_id, user)
    out = []
    for st in repos.ingest.list_streams_for_session(session_id):
        d = st.to_dict()
        d["download_url"] = blob.download_ref(st.data_ref) if st.data_ref else None
        out.append(d)
    return out


@router.get("/{session_id}/gpx")
def download_gpx(session_id: uuid.UUID, request: Request):
    """Export this session's processed GPS track as a GPX file — always
    regenerated from ``gps.json`` (see ``services/gpx.py::build_gpx``), never
    the original raw upload bytes, so it's uniform whether the session came
    from a device or a manual GPX/CSV import."""
    user = current_user(request)
    _require_visible(session_id, user)
    streams = repos.ingest.list_streams_for_session(session_id)
    gps_stream = next((s for s in streams if s.sensor_type == "gps" and s.data_ref), None)
    if gps_stream is None:
        raise HTTPException(404, "No GPS track for this session")
    points = load_json_or_404(gps_stream.data_ref)
    return Response(
        content=gpx.build_gpx(points),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="session-{session_id}.gpx"'},
    )


@router.get("/{session_id}/stats")
def get_stats(session_id: uuid.UUID, request: Request):
    user = current_user(request)
    _require_visible(session_id, user)
    stats = repos.sessions.get_stats(session_id)
    if stats is None:
        raise HTTPException(404, "No stats computed yet")
    return stats.to_dict()


@router.get("/{session_id}/analysis")
def get_analysis(session_id: uuid.UUID, request: Request):
    """The worker's analysis, assembled from its normalized DB homes: discrete
    tacks/gybes (``session_maneuvers``) and legs (``session_legs``) as rows, plus
    the JSON matrices/series/distributions (``session_analysis``). The polar
    curve and scalar stats have their own endpoints (``/polar-points``,
    ``/stats``). 404 until the pipeline has run (like ``/stats``)."""
    user = current_user(request)
    _require_visible(session_id, user)
    analysis = repos.sessions.get_analysis(session_id)
    maneuvers = repos.sessions.list_maneuvers(session_id)
    legs = repos.sessions.list_legs(session_id)
    if analysis is None and not maneuvers and not legs:
        raise HTTPException(404, "No analysis available")
    data = analysis.to_dict() if analysis is not None else {}
    data["maneuvers"] = [m.to_dict() for m in maneuvers]
    data["legs"] = [l.to_dict() for l in legs]
    return data


def _require_maneuver(session_id: uuid.UUID, maneuver_id: uuid.UUID):
    maneuver = repos.sessions.get_maneuver(maneuver_id)
    if maneuver is None or maneuver.session_id != session_id:
        raise HTTPException(404, "Maneuver not found")
    return maneuver


@router.patch("/{session_id}/maneuvers/{maneuver_id}")
def correct_maneuver(session_id: uuid.UUID, maneuver_id: uuid.UUID,
                     body: ManeuverCorrectionModel, request: Request):
    """User override of a detected maneuver's type (tack/gybe/course_change) —
    same edit-level permission as PATCH /sessions/{id}. Marks the row
    ``corrected_by_user`` and freezes ``original_maneuver_type`` at whatever
    the pipeline first assigned, so the maneuver-classifier training set
    (scripts/export_maneuver_training_data.py) can tell a human correction
    from the algorithm's raw guess.

    A correction survives a later reanalysis — see
    ``repos.sessions.upsert_maneuvers``/``services.maneuver_reconciliation``:
    a corrected row is never deleted, and a fresh candidate that turns out
    to describe the same event is dropped instead of duplicating it."""
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    _require_maneuver(session_id, maneuver_id)
    updated = repos.sessions.correct_maneuver(maneuver_id, body.maneuver_type)
    return updated.to_dict()


@router.patch("/{session_id}/maneuvers/{maneuver_id}/reject")
def reject_maneuver(session_id: uuid.UUID, maneuver_id: uuid.UUID,
                    body: ManeuverRejectionModel, request: Request):
    """User says a detected maneuver isn't real (``rejected: true``), or
    takes that back (``rejected: false``). Rejecting keeps the row instead
    of deleting it — a tombstone, so a later reanalysis's re-detection of
    the same event doesn't resurrect it as a fresh row (see
    ``services.maneuver_reconciliation``). Only valid for algorithm-origin
    rows; a manually-added one has no algorithm counterpart to resurrect,
    so it's deleted outright instead (``DELETE .../maneuvers/{id}``)."""
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    maneuver = _require_maneuver(session_id, maneuver_id)
    if maneuver.source == "manual":
        raise HTTPException(400, "Manual maneuvers cannot be rejected; delete instead")
    updated = repos.sessions.set_maneuver_rejected(maneuver_id, body.rejected)
    return updated.to_dict()


@router.delete("/{session_id}/maneuvers/{maneuver_id}")
def delete_maneuver(session_id: uuid.UUID, maneuver_id: uuid.UUID, request: Request):
    """Remove a manually-added maneuver outright — safe because there's no
    algorithm-detected counterpart that could reappear and duplicate it
    (unlike an algorithm-origin row, which uses the reject endpoint above so
    reanalysis can't resurrect it)."""
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    maneuver = _require_maneuver(session_id, maneuver_id)
    if maneuver.source != "manual":
        raise HTTPException(400, "Only manually-added maneuvers can be deleted; reject instead")
    repos.sessions.delete_maneuver(maneuver_id)
    return {"ok": True}


def _run_compute_maneuver(maneuver_id: uuid.UUID, maneuver_type: str,
                          start_time: float, end_time: float, prefix: str) -> None:
    try:
        ingestion.dispatch_maneuver_compute(
            ingestion.bucket_name(), prefix, maneuver_id, maneuver_type, start_time, end_time,
        )
    except Exception:
        logger.warning("maneuver compute job failed for %s", maneuver_id, exc_info=True)


@router.post("/{session_id}/maneuvers", status_code=202)
def add_maneuver(session_id: uuid.UUID, body: ManeuverCreateModel, request: Request,
                 background_tasks: BackgroundTasks):
    """Add a maneuver the algorithm missed, given the time window a user
    picked (e.g. two clicks on the session track — see the frontend's
    maneuver-edit mode). Inserts a ``pending`` placeholder immediately
    (``source='manual'``, stat columns at a 0.0 sentinel) so it's visible
    right away and already "preserved" against any reanalysis that starts in
    the meantime, then dispatches the worker in the background to compute
    real stats/features for the window (reusing the same math a detected
    maneuver gets — see ``processing/maneuvers.py::compute_manual_maneuver``).
    Poll ``GET .../analysis`` until the row's ``pending`` flips false."""
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    if body.end_time <= body.start_time:
        raise HTTPException(422, "end_time must be after start_time")
    upload = _latest_upload_or_404(session_id)
    maneuver = repos.sessions.add_manual_maneuver(
        session_id, body.maneuver_type, body.start_time, body.end_time,
    )
    prefix = ingestion.processed_prefix(upload.id)
    background_tasks.add_task(
        _run_compute_maneuver, maneuver.id, body.maneuver_type, body.start_time, body.end_time, prefix,
    )
    return {"ok": True, "maneuver_id": maneuver.id, "status": "pending"}


# --- crew ------------------------------------------------------------------------

@router.get("/{session_id}/crew")
def list_crew(session_id: uuid.UUID, request: Request):
    user = current_user(request)
    _require_visible(session_id, user)
    return [with_user(c.to_dict(), c.user_id) for c in repos.sessions.list_crew(session_id)]


@router.post("/{session_id}/crew")
def add_crew(session_id: uuid.UUID, body: SessionCrewModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    # Boat owner/admin adds anyone; a user may add themselves (guest aboard).
    if body.user_id != user.id and not _can_edit(session, user):
        raise HTTPException(403, "Boat owner/admin required")
    if repos.users.get_by_id(body.user_id) is None:
        raise HTTPException(404, "User not found")
    if not repos.sessions.add_crew(session_id, user_id=body.user_id,
                                   sailing_role=body.sailing_role):
        raise HTTPException(409, "Already in the crew")
    return {"ok": True}


@router.delete("/{session_id}/crew/{user_id}")
def remove_crew(session_id: uuid.UUID, user_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if user.id != user_id and not _can_edit(session, user):
        raise HTTPException(403, "Boat owner/admin required (or remove yourself)")
    if not repos.sessions.remove_crew(session_id, user_id):
        raise HTTPException(404, "Not in the crew")
    return {"ok": True}


# --- photos / videos ----------------------------------------------------------------

@router.get("/{session_id}/photos")
def list_photos(session_id: uuid.UUID, request: Request):
    user = current_user(request)
    _require_visible(session_id, user)
    return [
        p for p in (media.image_payload(ph.image_id)
                    for ph in repos.sessions.list_photos(session_id))
        if p is not None
    ]


@router.post("/{session_id}/photos")
def create_photo(session_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _is_crew_or_manager(session, user):
        raise HTTPException(403, "Session crew or boat owner/admin required")
    payload = media.create_image_upload(user.id)
    repos.sessions.add_photo(session_id, image_id=payload["image_id"], created_by=user.id)
    return payload


@router.post("/{session_id}/photos/{image_id}/confirm")
def confirm_photo(session_id: uuid.UUID, image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _is_crew_or_manager(session, user):
        raise HTTPException(403, "Session crew or boat owner/admin required")
    if repos.sessions.get_photo(session_id, image_id) is None:
        raise HTTPException(404, "Photo not found")
    if not media.confirm_image(image_id):
        raise HTTPException(409, "Image not uploaded yet")
    return {"ok": True}


@router.delete("/{session_id}/photos/{image_id}")
def delete_photo(session_id: uuid.UUID, image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    link = repos.sessions.get_photo(session_id, image_id)
    if link is None:
        raise HTTPException(404, "Photo not found")
    # created_by, or boat owner/admin (matrix).
    if link.created_by != user.id and not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    repos.sessions.remove_photo(session_id, image_id)
    media.delete_image(image_id, user.id)
    return {"ok": True}


@router.get("/{session_id}/videos")
def list_videos(session_id: uuid.UUID, request: Request):
    user = current_user(request)
    _require_visible(session_id, user)
    return [
        v for v in (media.file_payload(sv.file_id)
                    for sv in repos.sessions.list_videos(session_id))
        if v is not None
    ]


@router.post("/{session_id}/videos")
def create_video(session_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _is_crew_or_manager(session, user):
        raise HTTPException(403, "Session crew or boat owner/admin required")
    payload = media.create_file_upload(user.id, content_type="video/mp4")
    repos.sessions.add_video(session_id, file_id=payload["file_id"], created_by=user.id)
    return payload


@router.post("/{session_id}/videos/{file_id}/confirm")
def confirm_video(session_id: uuid.UUID, file_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    if not _is_crew_or_manager(session, user):
        raise HTTPException(403, "Session crew or boat owner/admin required")
    if repos.sessions.get_video(session_id, file_id) is None:
        raise HTTPException(404, "Video not found")
    if not media.confirm_file(file_id):
        raise HTTPException(409, "Video not uploaded yet")
    return {"ok": True}


@router.delete("/{session_id}/videos/{file_id}")
def delete_video(session_id: uuid.UUID, file_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    session = _require_session(session_id)
    link = repos.sessions.get_video(session_id, file_id)
    if link is None:
        raise HTTPException(404, "Video not found")
    if link.created_by != user.id and not _can_edit(session, user):
        raise HTTPException(403, "Not allowed")
    repos.sessions.remove_video(session_id, file_id)
    media.delete_file(file_id, user.id)
    return {"ok": True}
