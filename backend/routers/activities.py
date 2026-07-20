"""Activity endpoints (``/api/activities``) + per-activity marks.

Visibility follows ``activities.visibility`` (public|club|group|private) via
``activity_visible_to``; edits by the creator, club-scoped ``activity.manage``
holders, or superadmin — except changing ``visibility`` itself on a
club-linked activity, which requires club-scoped ``activity.manage`` (see
``can_change_activity_visibility``), not just being the creator. Marks:
activity creator, or ``mark.manage`` scoped to the club for race activities.
Creating a club-linked activity requires ``activity.manage`` on that club; a
group-linked one requires an owner/admin role in that group.
"""

import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from ..auth import (
    activity_visible_to,
    can_change_activity_visibility,
    can_edit_activity,
    current_user,
    require_user,
    user_has_permission,
    verify_csrf,
)
from ..db.models.activity import MARK_ROLES
from ..schemas import ActivityWriteModel, MarkWriteModel
from ..services import ingestion, media
from ._common import activity_sensor_data, repos

router = APIRouter(prefix="/api/activities", tags=["activities"])


def _with_thumbnail(activity) -> dict:
    d = activity.to_dict()
    d["thumbnail"] = media.image_payload(activity.thumbnail_image_id)
    return d


def _require_activity(activity_id: uuid.UUID):
    activity = repos.activities.get(activity_id)
    if activity is None:
        raise HTTPException(404, "Activity not found")
    return activity


def _require_visible(activity_id: uuid.UUID, user):
    activity = _require_activity(activity_id)
    if not activity_visible_to(activity, user):
        raise HTTPException(404, "Activity not found")  # don't reveal private ones
    return activity


def _can_manage_marks(activity, user) -> bool:
    if can_edit_activity(activity, user):
        return True
    # Race officers manage marks of club race activities.
    if activity.type == "race" and activity.club_id is not None:
        return user_has_permission(user, "mark.manage", club_id=activity.club_id)
    return False


@router.get("")
def list_activities(request: Request, type: Optional[str] = None,
                    club_id: Optional[uuid.UUID] = None,
                    group_id: Optional[uuid.UUID] = None,
                    status: Optional[str] = None,
                    mine: bool = False,
                    member_clubs: bool = False,
                    limit: Optional[int] = Query(None, le=100, gt=0),
                    offset: int = Query(0, ge=0)):
    user = current_user(request)
    if (mine or member_clubs) and user is None:
        raise HTTPException(401, "Authentication required")
    activities = repos.activities.list(
        club_id=club_id, group_id=group_id, type=type, status=status,
        created_by=user.id if mine else None,
        member_of_user=user.id if member_clubs else None,
        viewer_id=user.id if user else None,
        viewer_is_superadmin=bool(user and user.is_superadmin),
        limit=limit, offset=offset,
    )
    return [_with_thumbnail(a) for a in activities]


@router.get("/upcoming")
def list_upcoming_activities(request: Request, limit: int = 5):
    """Announced events from the caller's own clubs/groups, soonest first —
    powers the "in arrivo" banner in the personal diary. Registered before
    ``/{activity_id}`` so FastAPI doesn't try to parse "upcoming" as a UUID."""
    user = require_user(request)
    activities = repos.activities.list_upcoming_for_user(user.id, limit=limit)
    return [_with_thumbnail(a) for a in activities if activity_visible_to(a, user)]


@router.get("/{activity_id}")
def get_activity(activity_id: uuid.UUID, request: Request):
    return _with_thumbnail(_require_visible(activity_id, current_user(request)))


@router.post("")
def create_activity(body: ActivityWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if not body.type:
        raise HTTPException(422, "type is required")
    if body.club_id is not None and not user.is_superadmin:
        if repos.clubs.get(body.club_id) is None:
            raise HTTPException(404, "Club not found")
        if not user_has_permission(user, "activity.manage", club_id=body.club_id):
            raise HTTPException(403, "Not allowed to create activities for this club")
    if body.group_id is not None and not user.is_superadmin:
        if repos.groups.get(body.group_id) is None:
            raise HTTPException(404, "Group not found")
        if not repos.groups.is_member(body.group_id, user.id, roles=["owner", "admin"]):
            raise HTTPException(403, "Not allowed to create activities for this group")
    data = body.model_dump(exclude_unset=True)
    data["created_by"] = user.id
    return repos.activities.create(data).to_dict()


@router.patch("/{activity_id}")
def update_activity(activity_id: uuid.UUID, body: ActivityWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    activity = _require_activity(activity_id)
    if not can_edit_activity(activity, user):
        raise HTTPException(403, "Not allowed")
    data = body.model_dump(exclude_unset=True)
    if "visibility" in data and not can_change_activity_visibility(activity, user):
        raise HTTPException(403, "Not allowed to change visibility")
    return repos.activities.update(activity_id, data).to_dict()


@router.delete("/{activity_id}")
def delete_activity(activity_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    activity = _require_activity(activity_id)
    if not can_edit_activity(activity, user):
        raise HTTPException(403, "Not allowed")
    repos.activities.delete(activity_id)
    return {"ok": True}


@router.post("/{activity_id}/regenerate-thumbnail")
def regenerate_thumbnail(activity_id: uuid.UUID, request: Request):
    """Force a rebuild of the activity's overlay thumbnail, composited from
    every session's most recently processed track — for when the automatic
    post-analysis trigger (``system.py::upsert_session_analysis``) missed it,
    or a session was added/reprocessed after the last composite."""
    verify_csrf(request)
    user = require_user(request)
    activity = _require_activity(activity_id)
    if not can_edit_activity(activity, user):
        raise HTTPException(403, "Not allowed")
    prefixes = ingestion.activity_thumbnail_prefixes(activity_id)
    if not prefixes:
        raise HTTPException(404, "No processed sessions to render a thumbnail from")
    ingestion.dispatch_activity_thumbnail(ingestion.bucket_name(), activity_id, prefixes)
    return {"ok": True}


@router.get("/{activity_id}/sessions")
def list_activity_sessions(activity_id: uuid.UUID, request: Request):
    user = current_user(request)
    _require_visible(activity_id, user)
    return [media.session_thumbnail_payload(s) for s in repos.sessions.list(activity_id=activity_id)]


@router.get("/{activity_id}/data")
def get_activity_data(activity_id: uuid.UUID, request: Request,
                      sensors: str = "gps", pad_start: int = 0, pad_end: int = 0):
    """Time-aligned sensor data of every session in the activity, keyed by
    session id with boat info embedded — same shape as ``GET
    /races/{id}/data`` minus ``race_id``, for the activity's own overlay map."""
    activity = _require_visible(activity_id, current_user(request))
    start = activity.started_at - timedelta(seconds=pad_start) if activity.started_at else None
    end = activity.ended_at + timedelta(seconds=pad_end) if activity.ended_at else None
    out = activity_sensor_data(activity.id, sensors, start, end)
    return {"activity_id": activity_id, "sessions": out}


# --- marks ---------------------------------------------------------------------

@router.get("/{activity_id}/marks")
def list_marks(activity_id: uuid.UUID, request: Request):
    user = current_user(request)
    _require_visible(activity_id, user)
    return [m.to_dict() for m in repos.activities.list_marks(activity_id)]


@router.post("/{activity_id}/marks")
def add_mark(activity_id: uuid.UUID, body: MarkWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    activity = _require_activity(activity_id)
    if not _can_manage_marks(activity, user):
        raise HTTPException(403, "Not allowed")
    if body.mark_role is None or body.lat is None or body.lng is None:
        raise HTTPException(422, "mark_role, lat and lng are required")
    if body.mark_role not in MARK_ROLES:
        raise HTTPException(422, f"mark_role must be one of {MARK_ROLES}")
    return repos.activities.add_mark(activity_id, body.model_dump(exclude_unset=True)).to_dict()


@router.patch("/{activity_id}/marks/{mark_id}")
def update_mark(activity_id: uuid.UUID, mark_id: uuid.UUID,
                body: MarkWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    activity = _require_activity(activity_id)
    if not _can_manage_marks(activity, user):
        raise HTTPException(403, "Not allowed")
    mark = repos.activities.get_mark(mark_id)
    if mark is None or mark.activity_id != activity_id:
        raise HTTPException(404, "Mark not found")
    if body.mark_role is not None and body.mark_role not in MARK_ROLES:
        raise HTTPException(422, f"mark_role must be one of {MARK_ROLES}")
    return repos.activities.update_mark(mark_id, body.model_dump(exclude_unset=True)).to_dict()


@router.delete("/{activity_id}/marks/{mark_id}")
def delete_mark(activity_id: uuid.UUID, mark_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    activity = _require_activity(activity_id)
    if not _can_manage_marks(activity, user):
        raise HTTPException(403, "Not allowed")
    mark = repos.activities.get_mark(mark_id)
    if mark is None or mark.activity_id != activity_id:
        raise HTTPException(404, "Mark not found")
    repos.activities.delete_mark(mark_id)
    return {"ok": True}
