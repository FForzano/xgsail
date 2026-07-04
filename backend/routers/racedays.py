"""Race-day endpoints (``/api/racedays``).

Matrix: pub read; writes = ``raceday.manage`` scoped via the parent regatta's
club. Free race days (``regatta_id`` NULL) have no club scope, so creating or
editing them requires a GLOBAL grant or superadmin — scoped officers must
attach a regatta.
"""

import uuid
from datetime import date as date_t
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_permission, verify_csrf
from ..schemas import RaceDayWriteModel
from ._common import repos

router = APIRouter(prefix="/api/racedays", tags=["racedays"])


def _require_raceday(raceday_id: uuid.UUID):
    raceday = repos.racedays.get(raceday_id)
    if raceday is None:
        raise HTTPException(404, "Race day not found")
    return raceday


def _require_manage(request: Request, regatta_id: Optional[uuid.UUID]) -> None:
    club_id = None
    if regatta_id is not None:
        regatta = repos.regattas.get(regatta_id)
        if regatta is None:
            raise HTTPException(404, "Regatta not found")
        club_id = regatta.club_id
    # club_id=None → only global grants / superadmin pass (free race day).
    require_permission(request, "raceday.manage", club_id=club_id)


@router.get("")
def list_racedays(regatta_id: Optional[uuid.UUID] = None, date: Optional[date_t] = None):
    return [rd.to_dict() for rd in repos.racedays.list(regatta_id=regatta_id, date=date)]


@router.get("/{raceday_id}")
def get_raceday(raceday_id: uuid.UUID):
    d = _require_raceday(raceday_id).to_dict()
    d["races"] = [r.to_dict() for r in repos.races.list(race_day_id=raceday_id)]
    return d


@router.post("")
def create_raceday(body: RaceDayWriteModel, request: Request):
    verify_csrf(request)
    if body.date is None:
        raise HTTPException(422, "date is required")
    _require_manage(request, body.regatta_id)
    return repos.racedays.create(body.model_dump(exclude_unset=True)).to_dict()


@router.patch("/{raceday_id}")
def update_raceday(raceday_id: uuid.UUID, body: RaceDayWriteModel, request: Request):
    verify_csrf(request)
    raceday = _require_raceday(raceday_id)
    _require_manage(request, raceday.regatta_id)
    changes = body.model_dump(exclude_unset=True)
    if "regatta_id" in changes and changes["regatta_id"] != raceday.regatta_id:
        _require_manage(request, changes["regatta_id"])  # scope of the target too
    return repos.racedays.update(raceday_id, changes).to_dict()


@router.delete("/{raceday_id}")
def delete_raceday(raceday_id: uuid.UUID, request: Request):
    verify_csrf(request)
    raceday = _require_raceday(raceday_id)
    _require_manage(request, raceday.regatta_id)
    repos.racedays.delete(raceday_id)
    return {"ok": True}
