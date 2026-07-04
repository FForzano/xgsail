"""Polar curve endpoints (``/api/polar-points``).

Three granularities (exactly one target per curve, mirroring the DB CHECK):
class reference curves (pub read, superadmin write), boat empirical aggregates
(boat members read, owner/admin write), per-session polars (session
visibility; written by the processing pipeline via the system API).
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..auth import current_user, require_superadmin, require_user, session_visible_to, verify_csrf
from ..schemas import PolarUpsertModel
from ._common import repos

router = APIRouter(prefix="/api/polar-points", tags=["polars"])


def _one_target(class_id, boat_id, session_id) -> str:
    given = [n for n, v in (("class_id", class_id), ("boat_id", boat_id),
                            ("session_id", session_id)) if v is not None]
    if len(given) != 1:
        raise HTTPException(422, "Exactly one of class_id, boat_id, session_id is required")
    return given[0]


@router.get("")
def list_polar_points(request: Request,
                      class_id: Optional[uuid.UUID] = None,
                      boat_id: Optional[uuid.UUID] = None,
                      session_id: Optional[uuid.UUID] = None):
    target = _one_target(class_id, boat_id, session_id)
    user = current_user(request)
    if target == "boat_id":
        if user is None or not (user.is_superadmin or repos.boats.is_member(boat_id, user.id)):
            raise HTTPException(403, "Boat members only")
    elif target == "session_id":
        session = repos.sessions.get(session_id)
        if session is None or not session_visible_to(session, user):
            raise HTTPException(404, "Session not found")
    # class curves are public
    return [p.to_dict() for p in repos.polars.list(
        class_id=class_id, boat_id=boat_id, session_id=session_id)]


@router.put("")
def upsert_polar_curve(body: PolarUpsertModel, request: Request):
    verify_csrf(request)
    target = _one_target(body.class_id, body.boat_id, body.session_id)
    if target == "class_id":
        require_superadmin(request)
        if repos.boats.get_class(body.class_id) is None:
            raise HTTPException(404, "Boat class not found")
    elif target == "boat_id":
        user = require_user(request)
        if repos.boats.get(body.boat_id) is None:
            raise HTTPException(404, "Boat not found")
        if not (user.is_superadmin or repos.boats.is_member(
                body.boat_id, user.id, roles=["owner", "admin"])):
            raise HTTPException(403, "Boat owner/admin required")
    else:
        # Session polars come from the processing pipeline (system API), not users.
        raise HTTPException(403, "Session polars are written by the processing pipeline")
    count = repos.polars.bulk_upsert(
        class_id=body.class_id, boat_id=body.boat_id, session_id=body.session_id,
        source=body.source, points=[p.model_dump() for p in body.points],
    )
    return {"ok": True, "points": count}
