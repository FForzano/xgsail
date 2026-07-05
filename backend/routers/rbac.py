"""RBAC admin endpoints: role/permission catalog + ``user_roles`` grants.

Matrix: roles/permissions catalog = superadmin. Grants: superadmin may grant
anything; a club admin with ``user_role.manage_scoped`` may grant/revoke only
roles scoped to their own club (never global, never to arbitrary scopes).
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_superadmin, require_user, user_has_permission, verify_csrf
from ..schemas import UserRoleGrantModel
from ._common import repos

router = APIRouter(prefix="/api", tags=["rbac"])


@router.get("/roles")
def list_roles(request: Request):
    """Role catalog — any authenticated user (scoped managers need the ids to
    grant club roles; the catalog itself is not sensitive)."""
    require_user(request)
    return [r.to_dict() for r in repos.rbac.list_roles()]


@router.get("/permissions")
def list_permissions(request: Request):
    require_superadmin(request)
    return [p.to_dict() for p in repos.rbac.list_permissions()]


@router.get("/users/{user_id}/roles")
def list_user_roles(user_id: uuid.UUID, request: Request):
    user = require_user(request)
    rows = repos.rbac.list_user_roles(user_id=user_id)
    if user.id == user_id or user.is_superadmin:
        return [r.to_dict() for r in rows]
    # Scoped managers see only the grants inside clubs they manage.
    visible = [
        r for r in rows
        if r.scope_club_id is not None
        and user_has_permission(user, "user_role.manage_scoped", club_id=r.scope_club_id)
    ]
    return [r.to_dict() for r in visible]


@router.post("/user-roles")
def grant_user_role(body: UserRoleGrantModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if not user.is_superadmin:
        # Scoped managers: only club-scoped grants inside their own club.
        if body.scope_club_id is None:
            raise HTTPException(403, "Global grants require superadmin")
        if not user_has_permission(user, "user_role.manage_scoped",
                                   club_id=body.scope_club_id):
            raise HTTPException(403, "Not allowed for this club")
    role = repos.rbac.get_role(body.role_id)
    if role is None:
        raise HTTPException(404, "Role not found")
    if repos.users.get_by_id(body.user_id) is None:
        raise HTTPException(404, "User not found")
    grant = repos.rbac.grant_role(body.user_id, body.role_id,
                                  scope_club_id=body.scope_club_id)
    return grant.to_dict()


@router.delete("/user-roles/{user_role_id}")
def revoke_user_role(user_role_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    grant = repos.rbac.get_user_role(user_role_id)
    if grant is None:
        raise HTTPException(404, "Grant not found")
    if not user.is_superadmin:
        if grant.scope_club_id is None or not user_has_permission(
            user, "user_role.manage_scoped", club_id=grant.scope_club_id
        ):
            raise HTTPException(403, "Not allowed")
    repos.rbac.revoke_user_role(user_role_id)
    return {"ok": True}
