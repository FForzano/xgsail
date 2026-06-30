"""Permission checks used by endpoints.

Two imperative guards, mirroring how endpoints already call
``require_admin(request)``:

- ``require_admin(request)`` — broad admin gate.
- ``require_permission(request, key, club_id=...)`` — fine-grained RBAC check.

Behaviour by mode:
- ``SAILFRAMES_ADMIN_BYPASS`` set → always allowed (self-hosted dev).
- metadata backend != postgres → no RBAC store, fall back to the Cloudflare
  cookie gate (preserves today's protection level).
- metadata backend == postgres → resolve the user from a trusted identity
  header and evaluate roles/permissions (with club scope).

Until the login/token flow ships (the documented follow-up), the user identity
in Postgres mode comes from a reverse-proxy-injected header
(``SAILFRAMES_AUTH_EMAIL_HEADER``, default ``X-Auth-Email``).
"""

import os
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import select

from .cloudflare import cloudflare_admin

ADMIN_PERMISSION = "admin"


def _is_postgres() -> bool:
    return os.environ.get("SAILFRAMES_METADATA_BACKEND", "object").lower() == "postgres"


def _identity_email(request: Request) -> Optional[str]:
    header = os.environ.get("SAILFRAMES_AUTH_EMAIL_HEADER", "X-Auth-Email")
    return request.headers.get(header)


def _resolve_user(session, email: str):
    from ..db.models import UserORM

    return session.scalars(
        select(UserORM).where(UserORM.email == email, UserORM.is_active.is_(True))
    ).first()


def _user_has_permission(session, user, key: str, club_id: Optional[int]) -> bool:
    from ..db.models import PermissionORM, RolePermissionORM

    if user.is_superadmin:
        return True
    perm = session.scalars(select(PermissionORM).where(PermissionORM.key == key)).first()
    if perm is None:
        return False
    for ur in user.roles:
        # Scoped grant must match the target club; global grant (NULL) always applies.
        if ur.scope_club_id is not None and club_id is not None and ur.scope_club_id != club_id:
            continue
        rp = session.scalars(
            select(RolePermissionORM).where(
                RolePermissionORM.role_id == ur.role_id,
                RolePermissionORM.permission_id == perm.id,
            )
        ).first()
        if rp:
            return True
    return False


def _check_postgres(request: Request, key: str, club_id: Optional[int]) -> bool:
    from ..db import get_sessionmaker

    email = _identity_email(request)
    if not email:
        raise HTTPException(403, "Authentication required")
    with get_sessionmaker()() as session:
        user = _resolve_user(session, email)
        if user is None:
            raise HTTPException(403, "Unknown user")
        if _user_has_permission(session, user, key, club_id):
            return True
    raise HTTPException(403, f"Permission denied: {key}")


def require_permission(request: Request, key: str, *, club_id: Optional[int] = None) -> bool:
    if os.environ.get("SAILFRAMES_ADMIN_BYPASS"):
        return True
    if not _is_postgres():
        return cloudflare_admin(request)
    return _check_postgres(request, key, club_id)


def require_admin(request: Request) -> bool:
    if os.environ.get("SAILFRAMES_ADMIN_BYPASS"):
        return True
    if not _is_postgres():
        return cloudflare_admin(request)
    return _check_postgres(request, ADMIN_PERMISSION, None)
