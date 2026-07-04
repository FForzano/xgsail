"""Regatta endpoints (``/api/regattas``).

Matrix: pub read; writes = ``regatta.manage`` scoped to the regatta's club
(club_admin / race_officer), superadmin always.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_permission, verify_csrf
from ..schemas import RegattaWriteModel
from ._common import repos

router = APIRouter(prefix="/api/regattas", tags=["regattas"])


def _require_regatta(regatta_id: uuid.UUID):
    regatta = repos.regattas.get(regatta_id)
    if regatta is None:
        raise HTTPException(404, "Regatta not found")
    return regatta


@router.get("")
def list_regattas(club_id: Optional[uuid.UUID] = None, status: Optional[str] = None):
    return [r.to_dict() for r in repos.regattas.list(club_id=club_id, status=status)]


@router.get("/{regatta_id}")
def get_regatta(regatta_id: uuid.UUID):
    d = _require_regatta(regatta_id).to_dict()
    d["race_days"] = [rd.to_dict() for rd in repos.racedays.list(regatta_id=regatta_id)]
    return d


@router.post("")
def create_regatta(body: RegattaWriteModel, request: Request):
    verify_csrf(request)
    if not body.name or body.club_id is None:
        raise HTTPException(422, "name and club_id are required")
    if repos.clubs.get(body.club_id) is None:
        raise HTTPException(404, "Club not found")
    require_permission(request, "regatta.manage", club_id=body.club_id)
    return repos.regattas.create(body.model_dump(exclude_unset=True)).to_dict()


@router.patch("/{regatta_id}")
def update_regatta(regatta_id: uuid.UUID, body: RegattaWriteModel, request: Request):
    verify_csrf(request)
    regatta = _require_regatta(regatta_id)
    require_permission(request, "regatta.manage", club_id=regatta.club_id)
    changes = body.model_dump(exclude_unset=True)
    changes.pop("club_id", None)  # a regatta doesn't change club
    return repos.regattas.update(regatta_id, changes).to_dict()


@router.delete("/{regatta_id}")
def delete_regatta(regatta_id: uuid.UUID, request: Request):
    verify_csrf(request)
    regatta = _require_regatta(regatta_id)
    require_permission(request, "regatta.manage", club_id=regatta.club_id)
    repos.regattas.delete(regatta_id)
    return {"ok": True}
