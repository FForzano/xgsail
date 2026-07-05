"""Session endpoints (``/api/sessions``).

A session is one boat's participation in an activity; visibility follows the
parent activity, with crew and boat members always able to see their own
sessions (``session_visible_to``). Data ingestion happens through the device
API / imports — here it's CRUD, crew, media, streams and stats reads.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..auth import current_user, require_user, session_visible_to, verify_csrf
from ..schemas import SessionCrewModel, SessionWriteModel
from ..services import media
from ..storage import BlobNotFound
from ._common import blob, repos

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


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
        return [s.to_dict() for s in repos.sessions.list_for_user(user.id)]
    sessions = repos.sessions.list(activity_id=activity_id, boat_id=boat_id)
    return [s.to_dict() for s in sessions if session_visible_to(s, user)]


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
    """analysis.json produced by the worker's analyze pass — one per upload;
    the first found wins (single-upload sessions are the standard case)."""
    user = current_user(request)
    _require_visible(session_id, user)
    for upload in repos.ingest.list_uploads(session_id=session_id):
        try:
            return blob.get_json(f"processed/uploads/{upload.id}/analysis.json")
        except BlobNotFound:
            continue
    raise HTTPException(404, "No analysis available")


# --- crew ------------------------------------------------------------------------

@router.get("/{session_id}/crew")
def list_crew(session_id: uuid.UUID, request: Request):
    user = current_user(request)
    _require_visible(session_id, user)
    return [c.to_dict() for c in repos.sessions.list_crew(session_id)]


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
