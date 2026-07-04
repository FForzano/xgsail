"""Activity endpoints (``/api/activities``) + per-activity marks.

Visibility follows ``activities.visibility`` (public|club|group|private) via
``activity_visible_to``; edits by the creator, club-scoped ``activity.manage``
holders, or superadmin. Marks: activity creator, or ``mark.manage`` scoped to
the club for race activities.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..auth import (
    activity_visible_to,
    can_edit_activity,
    current_user,
    require_user,
    user_has_permission,
    verify_csrf,
)
from ..schemas import ActivityWriteModel, MarkWriteModel
from ._common import repos

router = APIRouter(prefix="/api/activities", tags=["activities"])


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
                    mine: bool = False):
    user = current_user(request)
    if mine and user is None:
        raise HTTPException(401, "Authentication required")
    activities = repos.activities.list(
        club_id=club_id, group_id=group_id, type=type,
        created_by=user.id if mine else None,
    )
    return [a.to_dict() for a in activities if activity_visible_to(a, user)]


@router.get("/{activity_id}")
def get_activity(activity_id: uuid.UUID, request: Request):
    return _require_visible(activity_id, current_user(request)).to_dict()


@router.post("")
def create_activity(body: ActivityWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if not body.type:
        raise HTTPException(422, "type is required")
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
    return repos.activities.update(activity_id, body.model_dump(exclude_unset=True)).to_dict()


@router.delete("/{activity_id}")
def delete_activity(activity_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    activity = _require_activity(activity_id)
    if not can_edit_activity(activity, user):
        raise HTTPException(403, "Not allowed")
    repos.activities.delete(activity_id)
    return {"ok": True}


@router.get("/{activity_id}/sessions")
def list_activity_sessions(activity_id: uuid.UUID, request: Request):
    user = current_user(request)
    _require_visible(activity_id, user)
    return [s.to_dict() for s in repos.sessions.list(activity_id=activity_id)]


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
