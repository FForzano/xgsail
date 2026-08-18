"""Live-recording presence endpoints (``/api/live-recordings``).

"Someone is recording on this boat right now" — the signal that lets a second
crew member join the same outing on purpose, instead of discovering after the
fact that their track was merged into it (``services/ingestion.py::
find_or_create_session``).

Presence only: nothing here creates a session, an activity or an upload, and
nothing here is an authorization decision — the banner it feeds is a hint, and
every recording proceeds whether or not these calls ever succeed.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_user, verify_csrf
from ..schemas import LiveRecordingUpsertModel
from ._common import repos, user_summary

router = APIRouter(prefix="/api/live-recordings", tags=["live-recordings"])


def _payload(row) -> dict:
    boat = repos.boats.get(row.boat_id)
    activity = repos.activities.get(row.activity_id) if row.activity_id else None
    return {
        "id": row.id,
        "boat_id": row.boat_id,
        "boat_name": boat.name if boat is not None else None,
        "activity_id": row.activity_id,
        "activity_name": activity.name if activity is not None else None,
        "started_at": row.started_at,
        "last_seen_at": row.last_seen_at,
        "user_id": row.user_id,
        "user": user_summary(row.user_id),
    }


def _require_boat_member(boat_id: uuid.UUID, user):
    if repos.boats.get(boat_id) is None:
        raise HTTPException(404, "Boat not found")
    # Any role, `visitor` included: a guest aboard records too. Membership is
    # required only so a stranger cannot make a banner appear in someone's
    # diary — the boat picker on the recording screen offers nothing else.
    if not (user.is_superadmin or repos.boats.is_member(boat_id, user.id)):
        raise HTTPException(403, "Boat membership required")


@router.get("")
def list_live_recordings(request: Request, boat_id: Optional[uuid.UUID] = None):
    """Recordings running right now on the caller's boats, theirs excluded.

    Their own recording is already on screen in the app that is making it;
    what this answers is "is anybody *else* aboard recording this outing"."""
    user = require_user(request)
    boat_ids = [b.id for b in repos.boats.list_boats_for_user(user.id)]
    if boat_id is not None:
        boat_ids = [b for b in boat_ids if b == boat_id]
    rows = repos.live_recordings.list_active(boat_ids, exclude_user_id=user.id)
    return [_payload(r) for r in rows]


@router.put("")
def upsert_live_recording(body: LiveRecordingUpsertModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat_member(body.boat_id, user)
    row = repos.live_recordings.upsert(
        boat_id=body.boat_id,
        user_id=user.id,
        activity_id=body.activity_id,
        client_recording_id=body.client_recording_id,
    )
    # Bounded work on a call that already writes, in place of a scheduled job.
    repos.live_recordings.prune()
    return _payload(row)


@router.delete("")
def end_live_recording(boat_id: uuid.UUID, request: Request):
    """Stop advertising. Always succeeds — an end retried after the app was
    killed must not fail just because the row is already gone."""
    verify_csrf(request)
    user = require_user(request)
    repos.live_recordings.end(boat_id=boat_id, user_id=user.id)
    return {"ok": True}
