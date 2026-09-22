"""Club endpoints (``/api/clubs``).

Matrix: pub read; create = any authenticated user, who becomes ``club_admin``
scoped to the new club (RBAC grant, not a column); update/deactivate =
``club.manage`` scoped; membership approval = ``user_club.manage`` scoped;
self-join lands as ``invited``; delete is always ``is_active=false``.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from ..auth import (
    require_permission,
    require_user,
    user_has_permission,
    verify_csrf,
)
from ..schemas import ClubMemberModel, ClubMemberStatusModel, ClubWriteModel
from ..services import club_osm_match, media
from ._common import repos, with_user

router = APIRouter(prefix="/api/clubs", tags=["clubs"])


def _require_club(club_id: uuid.UUID):
    club = repos.clubs.get(club_id)
    if club is None:
        raise HTTPException(404, "Club not found")
    return club


# The club's own two links to an OSM element: the element it *is*, and the
# separate element that is its sailing school. Both UNIQUE, both checked by
# the same guard — one list so a third such field cannot be added to only one.
_OSM_REF_FIELDS = ("osm_ref", "school_osm_ref")


def _effective_ref(body: ClubWriteModel, club, field: str):
    """What the row will hold for ``field`` once this write lands: the body's
    value if it says anything, otherwise what is stored (nothing, on create)."""
    if field in body.model_fields_set:
        return getattr(body, field)
    return getattr(club, field) if club is not None else None


def _check_osm_refs_free(body: ClubWriteModel, *, club=None) -> None:
    """409 if another club has already spoken for an OSM element this write
    claims; 422 if the write would name one element in both of the club's own
    roles.

    Both columns are UNIQUE, so without this a collision surfaces as an
    unhandled IntegrityError (a 500). The lookup spans both of them at once
    (``SqlClubRepo.get_by_osm_ref``): an OSM element is one place, so an
    element another club declares *itself* to be is just as taken as one
    already recorded as some club's school. Re-setting a club's own current
    value is a no-op, not a conflict.

    A club naming its own ``osm_ref`` as its ``school_osm_ref`` is rejected
    instead of stored: that is the "linked" tier, where the school is tagged
    on the club's own element, there is only one element and ``osm_ref``
    already dedupes its pin. Storing it twice would buy nothing and leave a
    second copy to drift the moment the club re-claims a different element.
    """
    club_id = club.id if club is not None else None
    for field in _OSM_REF_FIELDS:
        if field not in body.model_fields_set:
            continue
        ref = getattr(body, field)
        if ref is None:
            continue
        holder = repos.clubs.get_by_osm_ref(ref)
        if holder is not None and holder.id != club_id:
            raise HTTPException(409, "That OpenStreetMap place is already linked to a club")

    own, school = (_effective_ref(body, club, f) for f in _OSM_REF_FIELDS)
    if own is not None and own == school:
        raise HTTPException(
            422,
            "school_osm_ref must be a separate element from the club's own "
            "osm_ref; set has_sailing_school instead",
        )


def _school_changes(body: ClubWriteModel) -> dict:
    """The write's changes with the two school fields made consistent (see
    ``club_osm_match.normalise_school_changes``), a contradiction surfacing as
    a 422 rather than a silent pick between what the caller asked for twice."""
    try:
        return club_osm_match.normalise_school_changes(
            body.model_dump(exclude_unset=True)
        )
    except club_osm_match.SchoolFieldsConflict as exc:
        raise HTTPException(422, str(exc)) from exc


def _club_payload(club) -> dict:
    d = club.to_dict()
    d["logo"] = media.image_payload(club.logo_id)
    return d


@router.get("")
def list_clubs():
    return [_club_payload(c) for c in repos.clubs.list()]


@router.get("/{club_id}")
def get_club(club_id: uuid.UUID):
    return _club_payload(_require_club(club_id))


@router.post("")
def create_club(body: ClubWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if not body.name:
        raise HTTPException(422, "name is required")
    _check_osm_refs_free(body)
    club = repos.clubs.create(_school_changes(body))
    repos.clubs.add_member(club.id, user_id=user.id, status="active")
    role = repos.rbac.get_role_by_name("club_admin")
    if role is not None:
        repos.rbac.grant_role(user.id, role.id, scope_club_id=club.id)
    return _club_payload(repos.clubs.get(club.id))


@router.patch("/{club_id}")
def update_club(club_id: uuid.UUID, body: ClubWriteModel, request: Request):
    verify_csrf(request)
    club = _require_club(club_id)
    require_permission(request, "club.manage", club_id=club_id)
    # Claiming an OSM element — the club itself or its sailing school — is a
    # management action on this club, so the existing club.manage gate above
    # is the right one, no extra permission.
    _check_osm_refs_free(body, club=club)
    return _club_payload(repos.clubs.update(club_id, _school_changes(body)))


@router.get("/{club_id}/osm-suggestions")
def list_osm_suggestions(club_id: uuid.UUID, request: Request):
    """Cached OSM sailing-club elements that plausibly *are* this club, so its
    managers can link it without first finding it on the explorer map — the
    mirror of ``GET /boats/claim-suggestions``.

    Reads only what ``osm_pois`` already holds: never an Overpass call, so an
    area nobody has browsed yields ``[]`` rather than a slow request. An empty
    list is also the answer when the club is already linked or has no
    coordinates to search around — nothing here is an error.
    """
    club = _require_club(club_id)
    require_permission(request, "club.manage", club_id=club_id)
    if club.osm_ref is not None or club.lat is None or club.lng is None:
        return []
    south, west, north, east = club_osm_match.bbox_for_radius(club.lat, club.lng)
    pois = repos.osm_pois.list_in_bbox(south, west, north, east,
                                       kind=club_osm_match.CLUB_KIND)
    taken = repos.clubs.osm_refs_taken([p.osm_ref for p in pois])
    return club_osm_match.rank_suggestions(club.lat, club.lng, club.name, pois,
                                           taken_refs=taken)


@router.get("/{club_id}/school-suggestion")
def get_school_suggestion(club_id: uuid.UUID, request: Request):
    """Evidence from the OSM cache that this club runs a sailing school, so
    its managers can be prompted to set ``has_sailing_school`` — which only
    ``PATCH /clubs/{id}`` does. Nothing here writes the flag.

    ``{"source": "linked"|"nearby"|null, "candidates": [...]}``. ``linked``
    is a fact about the element the club declared itself to be; ``nearby`` is
    proximity, which is all a centre-point cache can offer — see
    ``services/club_osm_match.py``. ``source: null`` with an empty list is
    the answer whenever there is nothing to suggest (the club already says it
    teaches, it has no linked element and no coordinates, or nothing is
    cached around it); like the sibling endpoint, none of that is an error.
    """
    club = _require_club(club_id)
    require_permission(request, "club.manage", club_id=club_id)
    # Also covers a school already recorded as its own element: a non-NULL
    # ``school_osm_ref`` implies the flag (the write path normalises it, see
    # ``club_osm_match.normalise_school_changes``), so there is no second
    # condition to keep in step here — and suggesting what a manager has
    # already confirmed would be pure noise.
    if club.has_sailing_school:
        return club_osm_match.no_school_suggestion()
    linked = (repos.osm_pois.get_by_osm_ref(club.osm_ref)
              if club.osm_ref is not None else None)
    nearby = ()
    if club.lat is not None and club.lng is not None:
        south, west, north, east = club_osm_match.bbox_for_radius(
            club.lat, club.lng, club_osm_match.SCHOOL_RADIUS_M
        )
        nearby = repos.osm_pois.list_in_bbox(south, west, north, east,
                                             kind=club_osm_match.SCHOOL_KIND)
    return club_osm_match.school_suggestion(linked, nearby, club_lat=club.lat,
                                            club_lng=club.lng)


@router.delete("/{club_id}")
def deactivate_club(club_id: uuid.UUID, request: Request):
    """Never a hard delete — history (regattas, members, boats) is preserved."""
    verify_csrf(request)
    _require_club(club_id)
    require_permission(request, "club.manage", club_id=club_id)
    repos.clubs.update(club_id, {"is_active": False})
    return {"ok": True}


# --- membership (user_clubs) -------------------------------------------------

@router.get("/{club_id}/members")
def list_members(club_id: uuid.UUID, request: Request):
    user = require_user(request)
    _require_club(club_id)
    members = repos.clubs.list_members(club_id)
    manages = user.is_superadmin or user_has_permission(
        user, "user_club.manage", club_id=club_id
    )
    if not manages:
        # Active members see the roster; outsiders (and invitees) only their own row.
        if repos.clubs.is_active_member(club_id, user.id):
            members = [m for m in members if m.status == "active" or m.user_id == user.id]
        else:
            members = [m for m in members if m.user_id == user.id]
    return [with_user(m.to_dict(), m.user_id) for m in members]


@router.post("/{club_id}/members")
def add_member(club_id: uuid.UUID, body: ClubMemberModel, request: Request):
    """Self-join lands as ``requested`` (a manager approves); a manager adding
    someone else lands as ``invited`` (the user accepts) unless an explicit
    status is given."""
    verify_csrf(request)
    user = require_user(request)
    _require_club(club_id)
    manages = user.is_superadmin or user_has_permission(
        user, "user_club.manage", club_id=club_id
    )
    target = body.user_id or user.id
    if target != user.id and not manages:
        raise HTTPException(403, "Only club managers add other users")
    if target == user.id and not manages:
        status = "requested"
    else:
        status = body.status or "invited"
    if repos.users.get_by_id(target) is None:
        raise HTTPException(404, "User not found")
    if not repos.clubs.add_member(club_id, user_id=target, status=status):
        raise HTTPException(409, "Already a member (or pending)")
    return {"ok": True, "status": status}


@router.patch("/{club_id}/members/{user_id}")
def set_member_status(club_id: uuid.UUID, user_id: uuid.UUID,
                      body: ClubMemberStatusModel, request: Request):
    """Managers set any status; the invited user may accept their own invite
    (``invited → active`` only — declining is the self ``DELETE``). A
    ``requested`` row can only be activated by a manager (approval)."""
    verify_csrf(request)
    user = require_user(request)
    _require_club(club_id)
    member = repos.clubs.get_member(club_id, user_id)
    if member is None:
        raise HTTPException(404, "Member not found")
    self_accept = (user.id == user_id and member.status == "invited"
                   and body.status == "active")
    if not self_accept:
        require_permission(request, "user_club.manage", club_id=club_id)
    if not repos.clubs.set_member_status(club_id, user_id, body.status):
        raise HTTPException(404, "Member not found")
    return {"ok": True}


@router.delete("/{club_id}/members/{user_id}")
def remove_member(club_id: uuid.UUID, user_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_club(club_id)
    if user.id != user_id:
        require_permission(request, "user_club.manage", club_id=club_id)
    if not repos.clubs.remove_member(club_id, user_id):
        raise HTTPException(404, "Member not found")
    return {"ok": True}


# --- logo ---------------------------------------------------------------------

@router.post("/{club_id}/logo")
def upload_logo(club_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_club(club_id)
    require_permission(request, "club.manage", club_id=club_id)
    payload = media.create_image_upload(user.id)
    repos.clubs.update(club_id, {"logo_id": payload["image_id"]})
    return payload


@router.post("/{club_id}/logo/{image_id}/confirm")
def confirm_logo(club_id: uuid.UUID, image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    club = _require_club(club_id)
    require_permission(request, "club.manage", club_id=club_id)
    if club.logo_id != image_id:
        raise HTTPException(404, "Logo not found")
    if not media.confirm_image(image_id):
        raise HTTPException(409, "Image not uploaded yet")
    return {"ok": True}
