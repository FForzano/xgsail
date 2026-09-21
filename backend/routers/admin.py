"""Operator diagnostics (``/api/admin``) — read-only, superadmin, audited.

The instance operator sometimes has to debug a problem on somebody else's
account: which boats they own, which outings they recorded, why a session looks
wrong. Every endpoint here is gated on ``users.is_superadmin`` (the flag, not an
RBAC permission) and writes one ``admin_access_log`` row, because an access this
broad should be on the record.

Deliberately read-only and deliberately narrow:

- no impersonation and no writes — an operator changes another user's data
  through the same endpoints everyone else uses, where the normal rules apply;
- crew notes are never served. ``sessions.notes`` is private to that session's
  crew and the boat's owner/admin (``auth.session_notes_visible_to``), and
  "superadmin" is not one of those audiences; the summary carries a
  ``has_notes`` boolean instead, which is all a diagnosis needs;
- no media bytes — the existing per-resource endpoints already serve those to a
  superadmin, under their own checks.

The profile itself is not re-implemented: ``GET /api/users/{user_id}`` already
serves it to a superadmin and ``UserORM.__wire_exclude__`` already keeps the
password hash and reset token off the wire. ``GET /api/admin/users/{user_id}``
is the *diagnostic summary* — that same profile plus the counts that say at a
glance whether an account is empty or has data the operator should go look at.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from ..auth import require_superadmin
from ..services import media
from ._common import activity_payload, boat_payload, repos, user_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_target(user_id: uuid.UUID):
    user = repos.users.get_by_id(user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


def _audit(actor, target_user_id: uuid.UUID, action: str) -> None:
    """Record one access. Best-effort: a failed log must not fail the read.

    The log is accountability, not a gate — the caller is already authenticated
    and authorized, and the data is already theirs to see. Failing the endpoint
    would take the operator's diagnostics away exactly when something is
    already broken, so the failure is made loud in the logs instead. ``actor``
    is None only under ``SAILFRAMES_ADMIN_BYPASS``, and an unattributed row is
    still worth more than no row.
    """
    try:
        repos.admin_log.record(
            actor_user_id=actor.id if actor is not None else None,
            target_user_id=target_user_id,
            action=action,
        )
    except Exception:
        logger.exception("admin access log write failed (action=%s, target=%s)",
                         action, target_user_id)


def _session_summary(session) -> dict:
    """Enough to spot the broken outing, with no crew-note text in it."""
    boat = repos.boats.get(session.boat_id)
    return {
        "id": session.id,
        "activity_id": session.activity_id,
        "boat_id": session.boat_id,
        "boat": {"id": boat.id, "name": boat.name, "sail_number": boat.sail_number}
        if boat else None,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "status": session.status,
        "notes_shared": session.notes_shared,
        "has_notes": bool((session.notes_plain or "").strip()),
    }


@router.get("/users/{user_id}")
def get_user_diagnostics(user_id: uuid.UUID, request: Request):
    actor = require_superadmin(request)
    user = _require_target(user_id)
    _audit(actor, user_id, "user.detail")
    profile = user.to_dict()
    profile["profile_image"] = media.image_payload(user.profile_image_id)
    return {
        "user": profile,
        "counts": {
            "boats": len(repos.boats.list_boats_for_user(user_id)),
            "activities": len(repos.activities.list(
                crewed_or_created_by=user_id, viewer_is_superadmin=True)),
            "sessions": len(repos.sessions.list_for_user(user_id)),
            "devices": len(repos.devices.list(owner_user_id=user_id)),
            "clubs": len(repos.clubs.list_memberships_for_user(user_id)),
            "groups": len(repos.groups.list_memberships_for_user(user_id)),
            "roles": len(repos.rbac.list_user_roles(user_id=user_id)),
        },
    }


@router.get("/users/{user_id}/boats")
def list_user_boats(user_id: uuid.UUID, request: Request):
    """Every boat the user is linked to, guest placeholders included —
    ``list_boats_for_user`` keeps them by design (they are the creator's own
    boats), and a guest boat is often exactly what the operator is chasing."""
    actor = require_superadmin(request)
    _require_target(user_id)
    _audit(actor, user_id, "user.boats")
    return [boat_payload(b, actor) for b in repos.boats.list_boats_for_user(user_id)]


@router.get("/users/{user_id}/activities")
def list_user_activities(user_id: uuid.UUID, request: Request,
                         limit: Optional[int] = Query(None, le=100, gt=0),
                         offset: int = Query(0, ge=0)):
    actor = require_superadmin(request)
    _require_target(user_id)
    _audit(actor, user_id, "user.activities")
    return [activity_payload(a) for a in repos.activities.list(
        crewed_or_created_by=user_id, viewer_is_superadmin=True,
        limit=limit, offset=offset,
    )]


@router.get("/users/{user_id}/sessions")
def list_user_sessions(user_id: uuid.UUID, request: Request,
                       limit: int = Query(50, le=100, gt=0),
                       offset: int = Query(0, ge=0)):
    """Paginated in the router: ``list_for_user`` returns the whole history."""
    actor = require_superadmin(request)
    _require_target(user_id)
    _audit(actor, user_id, "user.sessions")
    sessions = repos.sessions.list_for_user(user_id)
    return [_session_summary(s) for s in sessions[offset:offset + limit]]


@router.get("/access-log")
def list_access_log(request: Request,
                    target_user_id: Optional[uuid.UUID] = None,
                    limit: int = Query(50, le=200, gt=0),
                    offset: int = Query(0, ge=0)):
    """Who looked at whose data, newest first.

    Not itself audited: this reads the operator's own log, not a user's data.
    """
    require_superadmin(request)
    rows = repos.admin_log.list(target_user_id=target_user_id,
                                limit=limit, offset=offset)
    return [
        r.to_dict() | {
            "actor": user_summary(r.actor_user_id) if r.actor_user_id else None,
            "target": user_summary(r.target_user_id) if r.target_user_id else None,
        }
        for r in rows
    ]
