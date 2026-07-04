"""Club endpoints (``/api/clubs``).

Matrix: pub read; create = any authenticated user, who becomes ``club_admin``
scoped to the new club (RBAC grant, not a column); update/deactivate =
``club.manage`` scoped; membership approval = ``user_club.manage`` scoped;
self-join lands as ``invited``; delete is always ``is_active=false``.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from ..auth import (
    require_permission,
    require_user,
    user_has_permission,
    verify_csrf,
)
from ..schemas import ClubMemberModel, ClubMemberStatusModel, ClubWriteModel
from ..services import media
from ._common import repos

router = APIRouter(prefix="/api/clubs", tags=["clubs"])


def _require_club(club_id: uuid.UUID):
    club = repos.clubs.get(club_id)
    if club is None:
        raise HTTPException(404, "Club not found")
    return club


def _club_payload(club) -> dict:
    d = club.to_dict()
    d["logo"] = media.image_payload(club.logo_id)
    return d


@router.get("")
def list_clubs():
    return [_club_payload(c) for c in repos.clubs.list()]


@router.get("/{club_id}")
def get_club(club_id: uuid.UUID):
    return _club_payload(_require_club(club_id))


@router.post("")
def create_club(body: ClubWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if not body.name:
        raise HTTPException(422, "name is required")
    club = repos.clubs.create(body.model_dump(exclude_unset=True))
    repos.clubs.add_member(club.id, user_id=user.id, status="active")
    role = repos.rbac.get_role_by_name("club_admin")
    if role is not None:
        repos.rbac.grant_role(user.id, role.id, scope_club_id=club.id)
    return _club_payload(repos.clubs.get(club.id))


@router.patch("/{club_id}")
def update_club(club_id: uuid.UUID, body: ClubWriteModel, request: Request):
    verify_csrf(request)
    _require_club(club_id)
    require_permission(request, "club.manage", club_id=club_id)
    return _club_payload(repos.clubs.update(club_id, body.model_dump(exclude_unset=True)))


@router.delete("/{club_id}")
def deactivate_club(club_id: uuid.UUID, request: Request):
    """Never a hard delete — history (regattas, members, boats) is preserved."""
    verify_csrf(request)
    _require_club(club_id)
    require_permission(request, "club.manage", club_id=club_id)
    repos.clubs.update(club_id, {"is_active": False})
    return {"ok": True}


# --- membership (user_clubs) -------------------------------------------------

@router.get("/{club_id}/members")
def list_members(club_id: uuid.UUID, request: Request):
    user = require_user(request)
    _require_club(club_id)
    members = repos.clubs.list_members(club_id)
    if user.is_superadmin or user_has_permission(user, "user_club.manage", club_id=club_id):
        return [m.to_dict() | {"user_id": m.user_id} for m in members]
    own = [m for m in members if m.user_id == user.id]
    return [m.to_dict() | {"user_id": m.user_id} for m in own]


@router.post("/{club_id}/members")
def add_member(club_id: uuid.UUID, body: ClubMemberModel, request: Request):
    """Self-join lands as ``invited``; a scoped manager may add anyone directly
    ``active``."""
    verify_csrf(request)
    user = require_user(request)
    _require_club(club_id)
    manages = user.is_superadmin or user_has_permission(
        user, "user_club.manage", club_id=club_id
    )
    target = body.user_id or user.id
    if target != user.id and not manages:
        raise HTTPException(403, "Only club managers add other users")
    status = "invited"
    if manages and body.status:
        status = body.status
    if repos.users.get_by_id(target) is None:
        raise HTTPException(404, "User not found")
    if not repos.clubs.add_member(club_id, user_id=target, status=status):
        raise HTTPException(409, "Already a member (or pending)")
    return {"ok": True, "status": status}


@router.patch("/{club_id}/members/{user_id}")
def set_member_status(club_id: uuid.UUID, user_id: uuid.UUID,
                      body: ClubMemberStatusModel, request: Request):
    verify_csrf(request)
    _require_club(club_id)
    require_permission(request, "user_club.manage", club_id=club_id)
    if not repos.clubs.set_member_status(club_id, user_id, body.status):
        raise HTTPException(404, "Member not found")
    return {"ok": True}


@router.delete("/{club_id}/members/{user_id}")
def remove_member(club_id: uuid.UUID, user_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_club(club_id)
    if user.id != user_id:
        require_permission(request, "user_club.manage", club_id=club_id)
    if not repos.clubs.remove_member(club_id, user_id):
        raise HTTPException(404, "Member not found")
    return {"ok": True}


# --- logo ---------------------------------------------------------------------

@router.post("/{club_id}/logo")
def upload_logo(club_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_club(club_id)
    require_permission(request, "club.manage", club_id=club_id)
    payload = media.create_image_upload(user.id)
    repos.clubs.update(club_id, {"logo_id": payload["image_id"]})
    return payload


@router.post("/{club_id}/logo/{image_id}/confirm")
def confirm_logo(club_id: uuid.UUID, image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    club = _require_club(club_id)
    require_permission(request, "club.manage", club_id=club_id)
    if club.logo_id != image_id:
        raise HTTPException(404, "Logo not found")
    if not media.confirm_image(image_id):
        raise HTTPException(409, "Image not uploaded yet")
    return {"ok": True}
