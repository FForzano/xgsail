"""Group endpoints (``/api/groups``).

Matrix: read pub if ``visibility=public`` else members only; create = auth
(creator becomes ``user_groups.role=owner``); update owner/admin; delete owner
(soft). Membership: invites by owner/admin land as ``status=invited`` (the
invitee accepts via PATCH on their own row, or declines via self DELETE);
self-join on public groups lands as ``requested`` (a manager approves); role
changes by owner.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from ..auth import current_user, require_user, verify_csrf
from ..schemas import GroupMemberModel, GroupMemberUpdateModel, GroupWriteModel
from ..services import media
from ._common import repos, with_user

router = APIRouter(prefix="/api/groups", tags=["groups"])


def _require_group(group_id: uuid.UUID):
    group = repos.groups.get(group_id)
    if group is None or group.deleted_at is not None:
        raise HTTPException(404, "Group not found")
    return group


def _can_read(group, user) -> bool:
    if group.visibility == "public":
        return True
    if user is None:
        return False
    return user.is_superadmin or repos.groups.is_member(group.id, user.id)


def _is_manager(user, group_id: uuid.UUID, *, owner_only: bool = False) -> bool:
    if user is None:
        return False
    if user.is_superadmin:
        return True
    roles = ["owner"] if owner_only else ["owner", "admin"]
    return repos.groups.is_member(group_id, user.id, roles=roles)


def _group_payload(group, *, include_members: bool) -> dict:
    d = group.to_dict()
    if include_members:
        d["members"] = [with_user(m.to_dict(), m.user_id)
                        for m in repos.groups.list_members(group.id)]
    else:
        d.pop("members", None)
    d["profile_image"] = media.image_payload(group.profile_image_id)
    return d


@router.get("")
def list_groups(request: Request, mine: bool = False):
    user = current_user(request)
    groups = [g for g in repos.groups.list() if g.deleted_at is None]
    if mine:
        if user is None:
            raise HTTPException(401, "Authentication required")
        groups = [g for g in groups if repos.groups.is_member(g.id, user.id)]
    else:
        groups = [g for g in groups if _can_read(g, user)]
    return [
        _group_payload(g, include_members=user is not None
                       and (user.is_superadmin or repos.groups.is_member(g.id, user.id)))
        for g in groups
    ]


@router.get("/{group_id}")
def get_group(group_id: uuid.UUID, request: Request):
    user = current_user(request)
    group = _require_group(group_id)
    if not _can_read(group, user):
        raise HTTPException(404, "Group not found")  # don't reveal private groups
    include = user is not None and (user.is_superadmin or repos.groups.is_member(group_id, user.id))
    return _group_payload(group, include_members=include)


@router.post("")
def create_group(body: GroupWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if not body.name:
        raise HTTPException(422, "name is required")
    data = body.model_dump(exclude_unset=True)
    data["created_by"] = user.id
    group = repos.groups.create(data)
    repos.groups.add_member(group.id, user_id=user.id, role="owner")
    return _group_payload(repos.groups.get(group.id), include_members=True)


@router.patch("/{group_id}")
def update_group(group_id: uuid.UUID, body: GroupWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_group(group_id)
    if not _is_manager(user, group_id):
        raise HTTPException(403, "Group owner/admin required")
    return _group_payload(repos.groups.update(group_id, body.model_dump(exclude_unset=True)),
                          include_members=True)


@router.delete("/{group_id}")
def delete_group(group_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_group(group_id)
    if not _is_manager(user, group_id, owner_only=True):
        raise HTTPException(403, "Group owner required")
    repos.groups.soft_delete(group_id, deleted_by=user.id)
    return {"ok": True}


# --- membership (user_groups) --------------------------------------------------

@router.post("/{group_id}/members")
def add_member(group_id: uuid.UUID, body: GroupMemberModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    group = _require_group(group_id)
    target = body.user_id or user.id
    if target == user.id and not _is_manager(user, group_id):
        # Self-join: allowed only on public groups (private = invite-only);
        # lands as a request pending owner/admin approval.
        if group.visibility != "public":
            raise HTTPException(403, "Private group: invite only")
        role, status = "member", "requested"
    else:
        if not _is_manager(user, group_id):
            raise HTTPException(403, "Group owner/admin required")
        role = body.role
        # Invites are pending until the invitee accepts (their own PATCH).
        status = "active" if target == user.id else "invited"
        if repos.users.get_by_id(target) is None:
            raise HTTPException(404, "User not found")
    if not repos.groups.add_member(group_id, user_id=target, role=role, status=status):
        raise HTTPException(409, "Already a member (or pending)")
    return {"ok": True, "status": status}


@router.patch("/{group_id}/members/{user_id}")
def update_member(group_id: uuid.UUID, user_id: uuid.UUID,
                  body: GroupMemberUpdateModel, request: Request):
    """Role changes = owner. Status: managers set any (incl. approving a
    ``requested`` row); the invited user may accept their own invite
    (``invited → active`` only — declining is the self ``DELETE``)."""
    verify_csrf(request)
    user = require_user(request)
    _require_group(group_id)
    member = repos.groups.get_member(group_id, user_id)
    if member is None:
        raise HTTPException(404, "Member not found")
    if body.role is not None:
        if not _is_manager(user, group_id, owner_only=True):
            raise HTTPException(403, "Group owner required")
        repos.groups.set_member_role(group_id, user_id, body.role)
    if body.status is not None:
        self_accept = (user.id == user_id and member.status == "invited"
                       and body.status == "active")
        if not self_accept and not _is_manager(user, group_id):
            raise HTTPException(403, "Group owner/admin required")
        repos.groups.set_member_status(group_id, user_id, body.status)
    return {"ok": True}


@router.delete("/{group_id}/members/{user_id}")
def remove_member(group_id: uuid.UUID, user_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_group(group_id)
    if user.id != user_id and not _is_manager(user, group_id):
        raise HTTPException(403, "Group owner/admin required (or leave yourself)")
    if not repos.groups.remove_member(group_id, user_id):
        raise HTTPException(404, "Member not found")
    return {"ok": True}


# --- profile image ---------------------------------------------------------------

@router.post("/{group_id}/profile-image")
def upload_profile_image(group_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_group(group_id)
    if not _is_manager(user, group_id):
        raise HTTPException(403, "Group owner/admin required")
    payload = media.create_image_upload(user.id)
    repos.groups.update(group_id, {"profile_image_id": payload["image_id"]})
    return payload


@router.post("/{group_id}/profile-image/{image_id}/confirm")
def confirm_profile_image(group_id: uuid.UUID, image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    group = _require_group(group_id)
    if not _is_manager(user, group_id):
        raise HTTPException(403, "Group owner/admin required")
    if group.profile_image_id != image_id:
        raise HTTPException(404, "Image not found")
    if not media.confirm_image(image_id):
        raise HTTPException(409, "Image not uploaded yet")
    return {"ok": True}
