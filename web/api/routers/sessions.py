"""Session metadata + management endpoints (``/api/sessions*``).

Sessions are recorded-data manifests (one device, one date); the bulk sensor
payloads stay in the blob store. This router covers listing, single fetch,
deletion, and the bulk cleanup of short/unassigned sessions.
"""

from fastapi import APIRouter, HTTPException, Query, Request

from .. import domain
from ..auth import (
    current_user,
    require_admin,
    require_user,
    session_visible_to,
    verify_csrf,
)
from ..schemas import SessionCrewModel
from ._common import (
    DATA_PREFIX,
    delete_prefix,
    list_keys,
    load_json_or_404,
    repos,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# Standing-crew roles on a boat that may edit its sessions' crew/attribution.
BOAT_MANAGE_ROLES = ["owner", "skipper"]


@router.get("")
def list_sessions(request: Request):
    """List race sessions visible to the caller.

    Stays open (no auth required) but the response is **filtered** by the
    visibility rule: an anonymous caller sees only ``public`` sessions; a
    logged-in caller also sees their own / crewed / club / group ones. Historical
    sessions backfilled to ``public`` keep showing, so the public dashboard is
    unaffected."""
    user = current_user(request)
    sessions = []
    for s in repos.sessions.list():
        if not session_visible_to(s, user):
            continue
        duration_sec = s.duration_sec or 0
        sessions.append({
            "device_id": s.device_id,
            "date": s.date,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "duration_sec": duration_sec,
            "duration_minutes": round(duration_sec / 60) if duration_sec else 0,
            "sensors": s.sensors if s.sensors is not None else [],
            "has_video": s.has_video,
            "has_analysis": s.has_analysis,
            "boat": s.boat,
            "name": s.name,
            "session_id": s.session_id,
            "visibility": s.visibility,
            "boat_id": s.boat_id,
        })

    return {"sessions": sorted(sessions, key=lambda s: s["date"], reverse=True)}


@router.get("/{device_id}/{date}")
def get_session(device_id: str, date: str, request: Request):
    """Get session metadata and manifest (subject to the visibility rule)."""
    session = repos.sessions.get(device_id, date)
    if session is None:
        raise HTTPException(404, f"Session not found: {device_id}/{date}")
    if not session_visible_to(session, current_user(request)):
        # 404 (not 403) so a private session isn't even confirmed to exist.
        raise HTTPException(404, f"Session not found: {device_id}/{date}")
    return session.to_dict()


def _can_edit_session(session: domain.Session, device_id: str, user) -> bool:
    """Owner/skipper of the attributed boat, whoever registered the device (for
    an unclaimed session), the session owner, or a superadmin."""
    if user.is_superadmin:
        return True
    if session.owner_user_id is not None and session.owner_user_id == user.id:
        return True
    if session.boat_id is not None and repos.boats.is_member(
        session.boat_id, user.id, roles=BOAT_MANAGE_ROLES
    ):
        return True
    if session.owner_user_id is None:
        device = repos.devices.get(device_id)
        if device is not None and device.registered_by == user.id:
            return True
    return False


@router.patch("/{device_id}/{date}/crew")
def edit_session_crew(device_id: str, date: str, body: SessionCrewModel, request: Request):
    """Edit a session's crew (guests allowed) and optionally claim its boat /
    set visibility. Writes to the deploy's authoritative store via the repo."""
    verify_csrf(request)
    user = require_user(request)
    session = repos.sessions.get(device_id, date)
    if session is None:
        raise HTTPException(404, f"Session not found: {device_id}/{date}")
    if not _can_edit_session(session, device_id, user):
        raise HTTPException(403, "Not allowed to edit this session")

    crew = []
    for slot in body.crew:
        if (slot.user_id is None) == (slot.guest_name is None):
            raise HTTPException(422, "Each crew slot needs exactly one of user_id / guest_name")
        crew.append(domain.SessionCrew(
            user_id=slot.user_id, guest_name=slot.guest_name, boat_role=slot.boat_role,
        ))
    session.crew = crew
    if body.boat_id is not None:
        session.boat_id = body.boat_id
    if body.visibility is not None:
        session.visibility = body.visibility
    if body.club_id is not None:
        session.club_id = body.club_id
    if body.group_id is not None:
        session.group_id = body.group_id
    # Claim an unclaimed session for the editor.
    if session.owner_user_id is None:
        session.owner_user_id = user.id

    repos.sessions.upsert(session)
    return repos.sessions.get(device_id, date).to_dict()


@router.delete("/{device_id}/{date}")
def delete_session(device_id: str, date: str, request: Request):
    """Delete a session and all its data (processed folder)."""
    require_admin(request)
    prefix = f"{DATA_PREFIX}/{device_id}/{date}/"
    deleted_count = delete_prefix(prefix)

    if deleted_count == 0:
        raise HTTPException(404, f"Session not found: {device_id}/{date}")

    return {
        "status": "deleted",
        "device_id": device_id,
        "date": date,
        "files_deleted": deleted_count,
    }


@router.post("/cleanup")
def cleanup_sessions(
    request: Request,
    max_duration_minutes: int = Query(15, description="Delete sessions shorter than this"),
    require_boat: bool = Query(True, description="Delete sessions with no boat selected"),
    dry_run: bool = Query(True, description="Preview without deleting"),
):
    """Bulk delete sessions that are too short or have no boat assigned.

    By default runs in dry_run mode - set dry_run=false to actually delete.
    """
    require_admin(request)
    # Get all sessions
    keys = list_keys(f"{DATA_PREFIX}/")
    manifests = [k for k in keys if k.endswith("manifest.json")]

    to_delete = []
    kept = []

    for key in manifests:
        try:
            manifest = load_json_or_404(key)
            parts = key.split("/")
            device_id = parts[1] if len(parts) > 2 else "unknown"
            date = parts[2] if len(parts) > 2 else "unknown"

            duration_sec = manifest.get("duration_sec", 0)
            duration_minutes = duration_sec / 60 if duration_sec else 0
            boat = manifest.get("boat")

            should_delete = False
            reason = []

            # Check duration
            if duration_minutes < max_duration_minutes:
                should_delete = True
                reason.append(f"duration {duration_minutes:.1f}min < {max_duration_minutes}min")

            # Check boat (only if require_boat is True and session is long enough)
            if require_boat and not boat and duration_minutes >= max_duration_minutes:
                should_delete = True
                reason.append("no boat selected")

            session_info = {
                "device_id": device_id,
                "date": date,
                "duration_minutes": round(duration_minutes, 1),
                "boat": boat,
                "name": manifest.get("name"),
            }

            if should_delete:
                session_info["reason"] = ", ".join(reason)
                to_delete.append(session_info)
            else:
                kept.append(session_info)

        except Exception:
            continue

    deleted_count = 0
    if not dry_run:
        for session in to_delete:
            prefix = f"{DATA_PREFIX}/{session['device_id']}/{session['date']}/"
            deleted_count += delete_prefix(prefix)

    return {
        "dry_run": dry_run,
        "criteria": {
            "max_duration_minutes": max_duration_minutes,
            "require_boat": require_boat,
        },
        "to_delete": to_delete,
        "to_delete_count": len(to_delete),
        "kept_count": len(kept),
        "files_deleted": deleted_count if not dry_run else 0,
    }
