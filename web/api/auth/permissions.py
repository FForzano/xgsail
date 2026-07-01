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

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import select

from .cloudflare import cloudflare_admin
from .tokens import ACCESS_COOKIE, CSRF_COOKIE, decode_access_token

ADMIN_PERMISSION = "admin"


def _is_postgres() -> bool:
    return os.environ.get("SAILFRAMES_METADATA_BACKEND", "object").lower() == "postgres"


def _header_email(request: Request) -> Optional[str]:
    header = os.environ.get("SAILFRAMES_AUTH_EMAIL_HEADER", "X-Auth-Email")
    return request.headers.get(header)


def current_user(request: Request):
    """Resolve the authenticated user (a ``domain.User``) or ``None``.

    Order: (1) access JWT from the ``sf_access`` cookie; (2) reverse-proxy
    identity header (self-hosted behind an auth proxy). Reads through the user
    repo, so it works on both metadata backends. Returns ``None`` for anonymous
    callers — it does NOT raise; use ``require_user`` when auth is mandatory.
    """
    from ..repositories import get_repos

    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        uid = decode_access_token(token)
        if uid is not None:
            u = get_repos().users.get_by_id(uid)
            if u is not None:
                return u
    email = _header_email(request)
    if email:
        return get_repos().users.get_by_email(email)
    return None


def require_user(request: Request):
    """Like ``current_user`` but 401s when unauthenticated."""
    u = current_user(request)
    if u is None:
        raise HTTPException(401, "Authentication required")
    return u


def session_visible_to(session, user) -> bool:
    """Phase 5 visibility rule (identical on both backends — operates on the
    domain ``Session`` + ``domain.User`` | None). See docs/user_plan.md →
    "Controllo accessi".

    Visible when: public; OR the caller owns it / is in its crew; OR the caller
    is standing crew of the attributed boat; OR visibility=club and the caller
    is an active club member; OR visibility=group and the caller is a group
    member; OR the caller is a superadmin. Anonymous callers see only public.
    """
    from ..repositories import get_repos

    if session.visibility == "public":
        return True
    if user is None:
        return False
    if user.is_superadmin:
        return True
    if session.owner_user_id is not None and session.owner_user_id == user.id:
        return True
    if any(c.user_id == user.id for c in (session.crew or [])):
        return True
    repos = get_repos()
    # Standing crew of the attributed boat always sees its own boat's data.
    if session.boat_id is not None and repos.boats.is_member(session.boat_id, user.id):
        return True
    if session.visibility == "club" and session.club_id is not None:
        if repos.clubs.is_active_member(session.club_id, user.id):
            return True
    if session.visibility == "group" and session.group_id is not None:
        if repos.groups.is_member(session.group_id, user.id):
            return True
    return False


def verify_csrf(request: Request) -> None:
    """Double-submit CSRF check, enforced only for cookie-authenticated
    requests (ambient auth). Header-auth / server-to-server callers (no access
    cookie) are exempt. Send ``X-SF-CSRF`` equal to the ``sf_csrf`` cookie on
    every state-changing request."""
    if not request.cookies.get(ACCESS_COOKIE):
        return
    header = request.headers.get("X-SF-CSRF")
    cookie = request.cookies.get(CSRF_COOKIE)
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise HTTPException(403, "CSRF check failed")


def _identity_email(request: Request) -> Optional[str]:
    """Email of the caller for RBAC checks: JWT access cookie first, then the
    reverse-proxy identity header. Keeps ``_check_postgres`` JWT-aware without
    changing its role/permission logic."""
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        uid = decode_access_token(token)
        if uid is not None:
            from ..repositories import get_repos

            u = get_repos().users.get_by_id(uid)
            if u is not None:
                return u.email
    return _header_email(request)


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
