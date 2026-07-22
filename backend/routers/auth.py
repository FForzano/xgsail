"""Native auth endpoints (``/api/auth/*``).

Email/password login issuing a short-lived JWT access token + a rotating,
reuse-detected refresh token. Backend-agnostic: users and refresh tokens are
persisted through the repository layer, so this works on both the object and
Postgres metadata backends.

Two transports for the same tokens, so both web and native (Capacitor)
clients are covered:
- **Web**: cookies. ``sf_access`` (httpOnly JWT, path ``/``), ``sf_refresh``
  (httpOnly opaque token, path ``/api/auth``), ``sf_csrf`` (readable by JS,
  mirrored back in ``X-SF-CSRF`` for the double-submit CSRF check on
  mutations). Same-origin only — this is what makes CSRF meaningful.
- **Native**: response body. ``access_token`` is sent as
  ``Authorization: Bearer`` on every request; ``refresh_token`` is stored
  client-side (secure storage) and sent back in the ``/refresh``/``/logout``
  body, since a cross-origin WebView cookie jar isn't reliable. Bearer
  requests never carry the access cookie, so CSRF never applies to them
  (see ``verify_csrf``).

Every login/refresh response includes both the cookies AND the token
fields — cookies for web, body fields for native (harmlessly ignored by
whichever client doesn't need them).
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response

from ..auth import (
    effective_capabilities,
    hash_password,
    require_user,
    verify_csrf,
    verify_password,
)
from ..auth.tokens import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    REFRESH_COOKIE_PATH,
    access_max_age,
    cookie_secure,
    hash_refresh,
    is_expired,
    issue_access_token,
    new_csrf_token,
    new_family_id,
    new_refresh_token,
    refresh_expiry,
    refresh_max_age,
)
from ..legal import CURRENT_PRIVACY_VERSION, CURRENT_TERMS_VERSION
from ..schemas import (
    AcceptLegalModel,
    ChangePasswordModel,
    LoginModel,
    SupportPromptModel,
    RefreshModel,
    RegisterModel,
)
from ._common import repos

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- cookie helpers -------------------------------------------------------

class _IssuedTokens:
    """Access + refresh + csrf issued together — cookies are set as a side
    effect on ``response``, and the raw values are also returned so the
    router can put ``access_token``/``refresh_token`` in the JSON body for
    native (Bearer) clients."""

    __slots__ = ("csrf", "access", "refresh")

    def __init__(self, csrf: str, access: str, refresh: str):
        self.csrf = csrf
        self.access = access
        self.refresh = refresh


def _set_auth_cookies(response: Response, user_id: uuid.UUID) -> _IssuedTokens:
    """Issue access+refresh+csrf, set them as cookies (web), and persist the
    refresh token row. Also returns the raw values for the JSON body
    (native)."""
    secure = cookie_secure()

    access = issue_access_token(user_id)
    response.set_cookie(
        ACCESS_COOKIE, access, httponly=True, secure=secure,
        samesite="lax", max_age=access_max_age(), path="/",
    )

    refresh = new_refresh_token()
    repos.auth_tokens.create(
        user_id=user_id,
        token_hash=hash_refresh(refresh),
        family_id=new_family_id(),
        issued_at=datetime.now(timezone.utc),
        expires_at=refresh_expiry(),
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh, httponly=True, secure=secure,
        samesite="lax", max_age=refresh_max_age(), path=REFRESH_COOKIE_PATH,
    )

    csrf = new_csrf_token()
    response.set_cookie(
        CSRF_COOKIE, csrf, httponly=False, secure=secure,
        samesite="lax", max_age=refresh_max_age(), path="/",
    )
    return _IssuedTokens(csrf, access, refresh)


def _rotate_refresh(
    response: Response, user_id: uuid.UUID, family_id: str, prev_id: uuid.UUID
) -> _IssuedTokens:
    """Issue a fresh access + rotated refresh in the same family."""
    secure = cookie_secure()

    access = issue_access_token(user_id)
    response.set_cookie(
        ACCESS_COOKIE, access, httponly=True, secure=secure,
        samesite="lax", max_age=access_max_age(), path="/",
    )

    refresh = new_refresh_token()
    repos.auth_tokens.create(
        user_id=user_id,
        token_hash=hash_refresh(refresh),
        family_id=family_id,
        prev_id=prev_id,
        issued_at=datetime.now(timezone.utc),
        expires_at=refresh_expiry(),
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh, httponly=True, secure=secure,
        samesite="lax", max_age=refresh_max_age(), path=REFRESH_COOKIE_PATH,
    )

    csrf = new_csrf_token()
    response.set_cookie(
        CSRF_COOKIE, csrf, httponly=False, secure=secure,
        samesite="lax", max_age=refresh_max_age(), path="/",
    )
    return _IssuedTokens(csrf, access, refresh)


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE, path="/")


# --- endpoints ------------------------------------------------------------

@router.post("/register")
def register(body: RegisterModel):
    """Create a user (never a superadmin). Login is a separate call."""
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(422, "Invalid email")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    # Accepting both the Terms of Service and the Privacy Policy is mandatory
    # to register — enforced here on the server, not just by the client-side
    # checkbox. The accepted versions are stamped from backend/legal.py so a
    # client can't claim to have accepted a different (e.g. older) version.
    if not body.terms_and_conditions:
        raise HTTPException(422, "You must accept the Terms of Service")
    if not body.privacy_policy:
        raise HTTPException(422, "You must accept the Privacy Policy")
    try:
        user = repos.users.create(
            email=email, password_hash=hash_password(body.password),
            first_name=body.first_name, last_name=body.last_name,
            terms_and_conditions=True,
            terms_version=CURRENT_TERMS_VERSION,
            privacy_version=CURRENT_PRIVACY_VERSION,
        )
    except ValueError:
        raise HTTPException(409, "Email already registered")
    return user.to_dict()


@router.post("/accept-legal")
def accept_legal(body: AcceptLegalModel, request: Request):
    """Record a logged-in user's (re-)acceptance of the current Terms of
    Service and/or Privacy Policy — used when a document changes and the app
    blocks on the re-acceptance gate (see capabilities ``legal``). Each flag
    accepts the *current* server-side version; a false flag leaves that
    document's previously-recorded acceptance untouched."""
    verify_csrf(request)
    user = require_user(request)
    repos.users.record_legal_acceptance(
        user.id,
        terms_version=CURRENT_TERMS_VERSION if body.terms_and_conditions else None,
        privacy_version=CURRENT_PRIVACY_VERSION if body.privacy_policy else None,
    )
    return {"ok": True}


@router.post("/support-prompt")
def support_prompt(body: SupportPromptModel, request: Request):
    """Record that the logged-in user dismissed the "Buy Me a Coffee"
    reminder banner (see capabilities ``support.shouldShow``), scheduling
    when it's next eligible to show again — sooner for a plain dismissal,
    much later once ``donated`` is confirmed."""
    verify_csrf(request)
    user = require_user(request)
    repos.users.record_support_prompt(user.id, donated=body.donated)
    return {"ok": True}


@router.post("/login")
def login(body: LoginModel, response: Response):
    email = body.email.strip().lower()
    stored = repos.users.get_password_hash_by_email(email)
    user = repos.users.get_by_email(email)
    # Constant-ish path: always run verify to avoid trivial user-enumeration.
    ok = verify_password(body.password, stored or "")
    if not stored or user is None or not user.is_active or not ok:
        raise HTTPException(401, "Invalid credentials")
    issued = _set_auth_cookies(response, user.id)
    return {
        "user": user.to_dict(),
        "csrf_token": issued.csrf,
        "access_token": issued.access,
        "refresh_token": issued.refresh,
        "expires_in": access_max_age(),
    }


@router.post("/refresh")
def refresh(request: Request, response: Response, body: Optional[RefreshModel] = None):
    # Body (native's explicit token) takes precedence when both are present.
    # Native's WebView is same-site with the API (see verify_csrf's comment),
    # so its sf_refresh cookie now gets attached ambiently too — but the
    # value native explicitly persisted client-side is the one guaranteed to
    # be current. Trusting the ambient cookie first risked presenting a
    # stale, already-rotated token whenever the two fell out of sync,
    # tripping reuse detection and force-revoking the whole session.
    presented = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if not presented:
        raise HTTPException(401, "No refresh token")
    row = repos.auth_tokens.get_by_hash(hash_refresh(presented))
    if row is None:
        raise HTTPException(401, "Invalid refresh token")
    # Reuse of an already-rotated/revoked token → compromise: nuke the family.
    if row.revoked_at:
        repos.auth_tokens.revoke_family(row.family_id, datetime.now(timezone.utc))
        _clear_auth_cookies(response)
        raise HTTPException(401, "Refresh token reuse detected")
    if is_expired(row.expires_at):
        _clear_auth_cookies(response)
        raise HTTPException(401, "Refresh token expired")
    # Rotate: mint a successor in the same family, revoke the presented one.
    issued = _rotate_refresh(response, row.user_id, row.family_id, row.id)
    repos.auth_tokens.revoke(row.id, datetime.now(timezone.utc))
    return {
        "csrf_token": issued.csrf,
        "access_token": issued.access,
        "refresh_token": issued.refresh,
        "expires_in": access_max_age(),
    }


@router.post("/change-password")
def change_password(body: ChangePasswordModel, request: Request, response: Response):
    """Verify the current password, set the new one, and revoke every refresh
    token (logs out all other sessions). Fresh cookies keep THIS session alive."""
    verify_csrf(request)
    user = require_user(request)
    stored = repos.users.get_password_hash_by_email(user.email)
    if not stored or not verify_password(body.current_password, stored):
        raise HTTPException(403, "Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    repos.users.update(user.id, {"password_hash": hash_password(body.new_password)})
    repos.auth_tokens.revoke_all_for_user(user.id, datetime.now(timezone.utc))
    issued = _set_auth_cookies(response, user.id)
    return {"ok": True, "csrf_token": issued.csrf}


@router.post("/logout")
def logout(request: Request, response: Response, body: Optional[RefreshModel] = None):
    # Same precedence as /refresh — see its comment.
    presented = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if presented:
        row = repos.auth_tokens.get_by_hash(hash_refresh(presented))
        if row is not None:
            repos.auth_tokens.revoke_family(row.family_id, datetime.now(timezone.utc))
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = require_user(request)
    return user.to_dict()


@router.get("/capabilities")
def capabilities(request: Request):
    """Roles + effective permissions (global vs per-club) + memberships, for a
    capability-aware UI. ``/me`` stays a cheap identity check; this is the
    heavier joined query the frontend caches. Server still authorizes every
    mutation — this only decides what UI to show."""
    user = require_user(request)
    return effective_capabilities(user)
