"""Regatta endpoints (``/api/regattas``).

Matrix: pub read; writes = ``regatta.manage`` scoped to the regatta's club
(club_admin / race_officer), superadmin always.

Exception to that matrix: the start list (``/entries``). Entering a boat is
gated on ``regatta.manage`` as usual, but ``/join`` lets any authenticated
sailor add a boat they own by presenting the regatta's share code — a club's
regatta is regularly sailed by visitors from other clubs, so club membership
is the wrong gate and the organizer cannot realistically pre-enter everyone.
The entry is what later authorizes attaching a recording to the race's
activity (see ``routers/sessions.py::attach_to_activity``); it is not the
official race entry, which stays with the organizing authority.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..auth import current_user, require_permission, require_user, verify_csrf
from ..auth.throttle import code_matches, new_code, throttle
from ..schemas import (
    OfficialStandingsUploadModel, RegattaEntryLinkModel, RegattaEntryWriteModel,
    RegattaJoinModel, RegattaWriteModel,
)
from ..services import media, scoring
from ._common import repos

router = APIRouter(prefix="/api/regattas", tags=["regattas"])

JOIN_CODE_LENGTH = 8


def _require_regatta(regatta_id: uuid.UUID):
    regatta = repos.regattas.get(regatta_id)
    if regatta is None:
        raise HTTPException(404, "Regatta not found")
    return regatta


def _require_manage(request: Request, regatta) -> None:
    require_permission(request, "regatta.manage", club_id=regatta.club_id)


def _regatta_payload(regatta) -> dict:
    d = regatta.to_dict()
    d["image"] = media.image_payload(regatta.image_id)
    return d


def _boat_summary(boat_id) -> Optional[dict]:
    """Minimal boat shape inlined in start-list and standings rows, so the
    client doesn't have to fetch each boat separately."""
    boat = repos.boats.get(boat_id)
    if boat is None:
        return None
    return {
        "id": boat.id,
        "name": boat.name,
        "sail_number": boat.sail_number,
        "boat_class_id": boat.boat_class_id,
    }


def _entry_payload(entry) -> dict:
    # An entry can vanish between the write and the read-back (e.g. its boat is
    # deleted concurrently, cascading the entry away), leaving nothing to serialize.
    if entry is None:
        raise HTTPException(404, "Entry not found")
    d = entry.to_dict()
    # Resolve boat info: if linked, read from boat record; if manual, use stored fields
    if entry.boat_id is not None:
        d["boat"] = _boat_summary(entry.boat_id)
        d["display_name"] = d["boat"]["name"] if d["boat"] else None
        d["display_sail_number"] = d["boat"]["sail_number"] if d["boat"] else None
    else:
        d["boat"] = None
        d["display_name"] = entry.boat_name
        d["display_sail_number"] = entry.sail_number
    # Exclude internal normalized field from API
    d.pop("boat_name_normalized", None)
    return d


def _regatta_races(regatta_id: uuid.UUID):
    """Race days of a regatta plus their races, in one query for the races.

    Returns ``(days, races_by_day)`` with days ordered by date and races by
    race number.
    """
    days = sorted(repos.racedays.list(regatta_id=regatta_id), key=lambda rd: rd.date)
    races_by_day: dict = {rd.id: [] for rd in days}
    for race in repos.races.list_for_racedays([rd.id for rd in days]):
        races_by_day[race.race_day_id].append(race)
    return days, races_by_day


@router.get("")
def list_regattas(request: Request, club_id: Optional[uuid.UUID] = None,
                  status: Optional[str] = None,
                  mine: bool = False, member_clubs: bool = False):
    if mine or member_clubs:
        user = current_user(request)
        if user is None:
            raise HTTPException(401, "Authentication required")
        if mine:
            regattas = repos.regattas.list_raced_by_user(user.id, status=status)
        else:
            regattas = repos.regattas.list_for_member_clubs(user.id, status=status)
    else:
        regattas = repos.regattas.list(club_id=club_id, status=status)
    return [_regatta_payload(r) for r in regattas]


@router.get("/upcoming")
def list_upcoming_regattas(request: Request, limit: int = 5):
    """Not-yet-completed regattas from the caller's own clubs, soonest first —
    the regatta half of the "in arrivo" banner in the personal diary (see
    ``GET /activities/upcoming`` for the activity half). Registered before
    ``/{regatta_id}`` so FastAPI doesn't try to parse "upcoming" as a UUID."""
    user = require_user(request)
    regattas = repos.regattas.list_upcoming_for_user(user.id, limit=limit)
    return [_regatta_payload(r) for r in regattas]


@router.get("/{regatta_id}")
def get_regatta(regatta_id: uuid.UUID):
    regatta = _require_regatta(regatta_id)
    d = _regatta_payload(regatta)
    days, races_by_day = _regatta_races(regatta_id)
    d["race_days"] = [{**rd.to_dict(),
                       "races": [r.to_dict() for r in races_by_day[rd.id]]}
                      for rd in days]
    return d


@router.get("/{regatta_id}/standings")
def get_standings(regatta_id: uuid.UUID):
    """Series standings, public like the rest of a regatta.

    If official standings have been published, they are returned instead of
    computed ones. Otherwise, standings are calculated from results:
    boats ranked = those with at least one result, plus the start list,
    so an entered boat that hasn't raced yet still shows up.
    """
    regatta = _require_regatta(regatta_id)
    days, races_by_day = _regatta_races(regatta_id)
    races = [race for rd in days for race in races_by_day[rd.id]]
    date_by_day = {rd.id: rd.date for rd in days}

    results_by_race: dict = {race.id: [] for race in races}
    for result in repos.races.list_results_for_races([race.id for race in races]):
        results_by_race[result.race_id].append(result)

    # Check for official standings first; use them if present
    official_standings = repos.regattas.list_official_standings(regatta_id)
    if official_standings:
        standings_rows = [
            {
                "rank": i + 1,
                "boat_id": os.boat_id,
                "position": os.position,
                "score": os.score,
                "status": os.status,
            }
            for i, os in enumerate(official_standings)
        ]
    else:
        all_entries = repos.regattas.list_entries(regatta_id)
        # Ranked/scored rows need a boat_id (results and standings positions
        # key on it), so manual entries with none are excluded here — but
        # entry_count (see total_entered_count) still counts them, for RRS A9.
        boat_ids = list(dict.fromkeys(
            [r.boat_id for race in races for r in results_by_race[race.id]]
            + [e.boat_id for e in all_entries if e.boat_id is not None]
        ))
        computed = scoring.compute_standings(
            races, results_by_race,
            scoring.total_entered_count(boat_ids, all_entries),
            regatta.scoring_system, boat_ids=boat_ids,
        )
        standings_rows = computed

    return {
        "scoring_system": regatta.scoring_system,
        "is_official": bool(official_standings),
        "races": [{"id": race.id, "race_number": race.race_number,
                   "date": date_by_day[race.race_day_id], "status": race.status}
                  for race in races],
        "standings": [{"rank": row["rank"], "total": row.get("total"),
                       "boat": _boat_summary(row["boat_id"]),
                       "races": {str(rid): v for rid, v in row.get("races", {}).items()}}
                      for row in standings_rows],
    }


@router.post("")
def create_regatta(body: RegattaWriteModel, request: Request):
    verify_csrf(request)
    if not body.name or body.club_id is None:
        raise HTTPException(422, "name and club_id are required")
    if repos.clubs.get(body.club_id) is None:
        raise HTTPException(404, "Club not found")
    require_permission(request, "regatta.manage", club_id=body.club_id)
    return _regatta_payload(repos.regattas.create(body.model_dump(exclude_unset=True)))


@router.patch("/{regatta_id}")
def update_regatta(regatta_id: uuid.UUID, body: RegattaWriteModel, request: Request):
    verify_csrf(request)
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)
    changes = body.model_dump(exclude_unset=True)
    changes.pop("club_id", None)  # a regatta doesn't change club
    return _regatta_payload(repos.regattas.update(regatta_id, changes))


@router.delete("/{regatta_id}")
def delete_regatta(regatta_id: uuid.UUID, request: Request):
    verify_csrf(request)
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)
    repos.regattas.delete(regatta_id)
    return {"ok": True}


# --- start list ---------------------------------------------------------------

def _require_own_boat(user, boat_id: uuid.UUID):
    """A sailor may only enter/withdraw a boat they own or administer."""
    if repos.boats.get(boat_id) is None:
        raise HTTPException(404, "Boat not found")
    if not (user.is_superadmin
            or repos.boats.is_member(boat_id, user.id, roles=["owner", "admin"])):
        raise HTTPException(403, "Not allowed to enter this boat")


@router.get("/{regatta_id}/entries")
def list_entries(regatta_id: uuid.UUID):
    """Public, like results: a start list is published information."""
    _require_regatta(regatta_id)
    return [_entry_payload(e) for e in repos.regattas.list_entries(regatta_id)]


@router.post("/{regatta_id}/entries")
def add_entry(regatta_id: uuid.UUID, body: RegattaEntryWriteModel, request: Request):
    """Add a boat to the start list: either a real boat (``boat_id``) or a
    manual entry (``boat_name``) for participants without an XGSail account."""
    verify_csrf(request)
    user = require_user(request)
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)

    # Linked entry: verify boat exists
    if body.boat_id is not None:
        if repos.boats.get(body.boat_id) is None:
            raise HTTPException(404, "Boat not found")

    entry = repos.regattas.add_entry(
        regatta_id, body.boat_id,
        boat_name=body.boat_name, sail_number=body.sail_number,
        source="organizer", created_by=user.id
    )
    return _entry_payload(entry)


@router.delete("/{regatta_id}/entries/{entry_id}")
def remove_entry(regatta_id: uuid.UUID, entry_id: uuid.UUID, request: Request):
    """Removable by the organizer or by the boat's own owner/admin — a sailor
    who self-entered can withdraw without chasing the race office."""
    verify_csrf(request)
    user = require_user(request)
    regatta = _require_regatta(regatta_id)

    entry = repos.regattas.get_entry_by_id(regatta_id, entry_id)
    if entry is None:
        raise HTTPException(404, "Entry not found")

    # Organizer can always remove, or boat owner/admin if entry is linked
    is_owner = (
        entry.boat_id is not None
        and (user.is_superadmin
             or repos.boats.is_member(entry.boat_id, user.id, roles=["owner", "admin"]))
    )
    if not is_owner:
        _require_manage(request, regatta)

    repos.regattas.remove_entry_by_id(entry_id)
    return {"ok": True}


@router.patch("/{regatta_id}/entries/{entry_id}")
def link_entry(regatta_id: uuid.UUID, entry_id: uuid.UUID,
               body: RegattaEntryLinkModel, request: Request):
    """Organizer linking a manual entry to a real boat. Idempotent if already
    linked to the same boat. Returns 409 if the boat is already entered separately."""
    verify_csrf(request)
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)

    entry = repos.regattas.get_entry_by_id(regatta_id, entry_id)
    if entry is None:
        raise HTTPException(404, "Entry not found")

    # Verify boat exists
    boat = repos.boats.get(body.boat_id)
    if boat is None:
        raise HTTPException(404, "Boat not found")

    # Check if this boat is already entered (elsewhere on this regatta)
    existing = repos.regattas.get_entry(regatta_id, body.boat_id)
    if existing is not None and existing.id != entry_id:
        raise HTTPException(409, "Boat is already entered on this regatta")

    updated = repos.regattas.link_entry(regatta_id, entry_id, body.boat_id)
    if updated is None:
        raise HTTPException(500, "Link failed")
    return _entry_payload(updated)


# --- official standings -------------------------------------------------------

@router.put("/{regatta_id}/official-standings")
def set_official_standings(regatta_id: uuid.UUID, body: OfficialStandingsUploadModel,
                           request: Request):
    """Publish official standings for a regatta, overriding computed standings.
    Requires regatta.manage permission. The standings provided replace any
    existing official standings."""
    verify_csrf(request)
    user = require_user(request)
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)

    standings_data = []
    for row in body.standings:
        # Verify each boat exists
        if repos.boats.get(row.boat_id) is None:
            raise HTTPException(404, f"Boat {row.boat_id} not found")
        standings_data.append(row.model_dump())

    repos.regattas.set_official_standings(regatta_id, standings_data, user.id)
    return {"ok": True, "count": len(standings_data)}


@router.delete("/{regatta_id}/official-standings")
def clear_official_standings(regatta_id: uuid.UUID, request: Request):
    """Delete official standings for a regatta, reverting to computed standings."""
    verify_csrf(request)
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)

    had_official = repos.regattas.clear_official_standings(regatta_id)
    return {"ok": True, "had_official": had_official}


@router.post("/{regatta_id}/join")
def join_regatta(regatta_id: uuid.UUID, body: RegattaJoinModel, request: Request):
    """Self-entry with the share code. Immediate, no organizer confirmation:
    the sailor typically does this on the beach on race morning, when nobody
    is at a desk to approve it. ``source="code"`` keeps self-entries visible
    to the organizer, who can remove them."""
    verify_csrf(request)
    throttle(request, bucket="regatta_join", max_per_min=10,
             message="Too many attempts, retry later")
    user = require_user(request)
    regatta = _require_regatta(regatta_id)
    _require_own_boat(user, body.boat_id)
    # Compared against THIS regatta's code (not looked up globally) so a valid
    # code for another regatta can't enter a boat here.
    if not code_matches(body.code, regatta.join_code):
        raise HTTPException(403, "Invalid or revoked code")
    entry = repos.regattas.add_entry(regatta_id, body.boat_id,
                                     boat_name=None, sail_number=None,
                                     source="code", created_by=user.id)
    return _entry_payload(entry)


# --- share code ---------------------------------------------------------------

@router.get("/{regatta_id}/join-code")
def get_join_code(regatta_id: uuid.UUID, request: Request):
    """Manage-gated: the code is excluded from the public regatta payload
    (``RegattaORM.__wire_exclude__``) and served only here."""
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)
    return {"join_code": regatta.join_code}


@router.post("/{regatta_id}/join-code")
def regenerate_join_code(regatta_id: uuid.UUID, request: Request):
    """Issue a fresh code, invalidating any link already handed out."""
    verify_csrf(request)
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)
    updated = repos.regattas.set_join_code(regatta_id, new_code(JOIN_CODE_LENGTH))
    return {"join_code": updated.join_code}


@router.delete("/{regatta_id}/join-code")
def revoke_join_code(regatta_id: uuid.UUID, request: Request):
    verify_csrf(request)
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)
    repos.regattas.set_join_code(regatta_id, None)
    return {"ok": True}


# --- image --------------------------------------------------------------------

@router.post("/{regatta_id}/image")
def upload_regatta_image(regatta_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)
    payload = media.create_image_upload(user.id)
    repos.regattas.update(regatta_id, {"image_id": payload["image_id"]})
    return payload


@router.post("/{regatta_id}/image/{image_id}/confirm")
def confirm_regatta_image(regatta_id: uuid.UUID, image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    regatta = _require_regatta(regatta_id)
    _require_manage(request, regatta)
    if regatta.image_id != image_id:
        raise HTTPException(404, "Image not found")
    if not media.confirm_image(image_id):
        raise HTTPException(409, "Image not uploaded yet")
    return {"ok": True}
