"""Boat endpoints (``/api/boats``, ``/api/boat-classes``).

Matrix: boats are pub-readable (sensitive docs cert/mbsa only for members),
creation makes the caller ``user_boats.role=owner``, writes follow the
per-resource ownership roles (owner = full, admin = write-no-delete).
Boat classes are a superadmin-managed catalog. Photos/documents are
parent-mediated media (presign + confirm). The notebook (``boat_notes``,
free-text rig-tuning entries) follows the same ownership roles: member-read,
owner/admin-write. A boat also exposes a read-only logbook view of its
sessions' crew notes, gated per session (``session_notes_visible_to``) rather
than by boat membership alone.

A *guest boat* (``boats.is_guest``) is a placeholder its creator owns like any
other boat; the real owner takes it over through ``boat_claims``, which only
that creator (or a superadmin) may approve — approving grants boat membership,
and boat membership is what gates read access to every session on the boat.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from ..auth import (
    current_user,
    require_superadmin,
    require_user,
    session_notes_visible_to,
    verify_csrf,
)
from ..auth.throttle import throttle
from ..schemas import (
    BoatClaimCreateModel,
    BoatClassWriteModel,
    BoatMemberModel,
    BoatMemberRoleModel,
    BoatNoteCreateModel,
    BoatNoteOrderModel,
    BoatNoteUpdateModel,
    BoatWriteModel,
)
from ..services import boat_merge, media
from ._common import repos, user_summary, with_user

router = APIRouter(prefix="/api", tags=["boats"])

_SENSITIVE = ("cert_id", "mbsa_id")


def _require_boat(boat_id: uuid.UUID):
    boat = repos.boats.get(boat_id)
    if boat is None:
        raise HTTPException(404, "Boat not found")
    return boat


def _is_manager(user, boat_id: uuid.UUID, *, owner_only: bool = False) -> bool:
    if user is None:
        return False
    if user.is_superadmin:
        return True
    roles = ["owner"] if owner_only else ["owner", "admin"]
    return repos.boats.is_member(boat_id, user.id, roles=roles)


def _boat_payload(boat, user) -> dict:
    """Public read shape — sensitive document refs only for members/sa."""
    d = boat.to_dict()
    is_member = user is not None and (
        user.is_superadmin or repos.boats.is_member(boat.id, user.id)
    )
    if is_member:
        d["cert"] = media.file_payload(boat.cert_id)
        d["mbsa"] = media.file_payload(boat.mbsa_id)
    else:
        for k in _SENSITIVE:
            d.pop(k, None)
        d.pop("members", None)
    d["photos"] = [
        p for p in (media.image_payload(ph.image_id) for ph in repos.boats.list_photos(boat.id))
        if p is not None
    ]
    return d


# --- boat classes (superadmin catalog) -------------------------------------

def _require_class(class_id: uuid.UUID):
    boat_class = repos.boats.get_class(class_id)
    if boat_class is None:
        raise HTTPException(404, "Boat class not found")
    return boat_class


def _class_payload(boat_class) -> dict:
    d = boat_class.to_dict()
    d["logo"] = media.image_payload(boat_class.logo_id)
    return d


@router.get("/boat-classes")
def list_boat_classes(limit: int = Query(50, le=1000, gt=0), offset: int = Query(0, ge=0),
                      search: Optional[str] = None, hull_type: Optional[str] = None,
                      sort: str = Query("name", pattern="^(name|py_rating|crew_size|rya_class_id)$"),
                      order: str = Query("asc", pattern="^(asc|desc)$")):
    return [_class_payload(c) for c in repos.boats.list_classes(
        limit=limit, offset=offset, search=search, hull_type=hull_type, sort=sort, order=order,
    )]


@router.post("/boat-classes")
def create_boat_class(body: BoatClassWriteModel, request: Request):
    verify_csrf(request)
    require_superadmin(request)
    if not body.name:
        raise HTTPException(422, "name is required")
    return _class_payload(repos.boats.create_class(body.model_dump(exclude_unset=True)))


@router.patch("/boat-classes/{class_id}")
def update_boat_class(class_id: uuid.UUID, body: BoatClassWriteModel, request: Request):
    verify_csrf(request)
    require_superadmin(request)
    updated = repos.boats.update_class(class_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(404, "Boat class not found")
    return _class_payload(updated)


@router.post("/boat-classes/{class_id}/logo")
def upload_class_logo(class_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    require_superadmin(request)
    _require_class(class_id)
    payload = media.create_image_upload(user.id)
    repos.boats.update_class(class_id, {"logo_id": payload["image_id"]})
    return payload


@router.post("/boat-classes/{class_id}/logo/{image_id}/confirm")
def confirm_class_logo(class_id: uuid.UUID, image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    require_superadmin(request)
    boat_class = _require_class(class_id)
    if boat_class.logo_id != image_id:
        raise HTTPException(404, "Logo not found")
    if not media.confirm_image(image_id):
        raise HTTPException(409, "Image not uploaded yet")
    return {"ok": True}


@router.delete("/boat-classes/{class_id}")
def delete_boat_class(class_id: uuid.UUID, request: Request):
    verify_csrf(request)
    require_superadmin(request)
    if not repos.boats.delete_class(class_id):
        raise HTTPException(404, "Boat class not found")
    return {"ok": True}


# --- boats ------------------------------------------------------------------

@router.get("/boats")
def list_boats(request: Request, mine: bool = False, q: Optional[str] = None,
               limit: Optional[int] = Query(None, le=100, gt=0),
               offset: int = Query(0, ge=0)):
    """``q`` searches name / sail number / class name — for pickers that must
    not pull the whole instance's boats into a select."""
    user = current_user(request)
    if mine:
        if user is None:
            raise HTTPException(401, "Authentication required")
        boats = repos.boats.list_boats_for_user(user.id)
    else:
        boats = repos.boats.list(q=q, limit=limit, offset=offset)
    return [_boat_payload(b, user) for b in boats]


# --- guest boats + claims ----------------------------------------------------
#
# Declared before ``/boats/{boat_id}``: FastAPI matches in declaration order,
# so "claimable" / "claims" would otherwise be parsed as a boat id and 422.

def _claimable_payload(boat) -> dict:
    """Deliberately not ``_boat_payload``: this is a "is this my boat?" search
    run by someone with no relationship to the boat, and a boat's full payload
    (members, documents, photos) belongs to the people already on it. Just
    enough to recognise the boat and see who entered it."""
    boat_class = repos.boats.get_class(boat.boat_class_id) if boat.boat_class_id else None
    return {
        "id": boat.id,
        "name": boat.name,
        "sail_number": boat.sail_number,
        "boat_class": boat_class.name if boat_class is not None else None,
        "session_count": repos.sessions.count_for_boat(boat.id),
        "created_by": user_summary(boat.guest_created_by) if boat.guest_created_by else None,
    }


@router.get("/boats/claimable")
def list_claimable_boats(request: Request, q: str = Query(...),
                         limit: int = Query(20, le=50, gt=0),
                         offset: int = Query(0, ge=0)):
    """Guest boats matching ``q``. Search-only, minimum two characters: the
    point is to find one known boat, not to enumerate every placeholder on the
    instance."""
    require_user(request)
    if len(q.strip()) < 2:
        raise HTTPException(422, "q must be at least 2 characters")
    return [_claimable_payload(b) for b in
            repos.boats.list_claimable(q=q.strip(), limit=limit, offset=offset)]


@router.get("/boats/claims/mine")
def list_my_claims(request: Request):
    """The caller's own claims, any status, so a pending or rejected one stays
    visible to the person who filed it."""
    user = require_user(request)
    out = []
    for claim in repos.boats.list_claims_by_user(user.id):
        boat = repos.boats.get(claim.boat_id)
        out.append(claim.to_dict() | {
            "boat": {"id": boat.id, "name": boat.name, "sail_number": boat.sail_number,
                     "is_guest": boat.is_guest} if boat is not None else None,
        })
    return out


@router.post("/boats/{boat_id}/claims")
def create_claim(boat_id: uuid.UUID, body: BoatClaimCreateModel, request: Request):
    """File a claim on a guest boat. Throttled: an authenticated caller could
    otherwise probe the instance for boats and spam their creators."""
    verify_csrf(request)
    throttle(request, bucket="boat_claim", max_per_min=5,
             message="Too many claims, retry later")
    user = require_user(request)
    boat = _require_boat(boat_id)
    if not boat.is_guest:
        raise HTTPException(409, "Boat is not claimable")
    if repos.boats.is_member(boat_id, user.id):
        raise HTTPException(409, "Already a member of this boat")
    if body.target_boat_id is not None:
        if body.target_boat_id == boat_id:
            raise HTTPException(422, "target_boat_id must be a different boat")
        if repos.boats.get(body.target_boat_id) is None:
            raise HTTPException(404, "Target boat not found")
        # A merge moves the guest boat's sessions onto the target, so the
        # claimant must manage the target — not merely be a member of it.
        if not _is_manager(user, body.target_boat_id):
            raise HTTPException(403, "Target boat owner/admin required")
    claim = repos.boats.create_claim(boat_id, user_id=user.id,
                                     target_boat_id=body.target_boat_id)
    if claim is None:
        raise HTTPException(409, "A pending claim already exists")
    return claim.to_dict()


@router.get("/boats/{boat_id}/claims")
def list_boat_claims(boat_id: uuid.UUID, request: Request,
                     status: Optional[str] = Query(None)):
    """Claims filed against this guest boat — owner/admin only: they are
    addressed to the person who has to decide them."""
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    return [with_user(c.to_dict(), c.user_id)
            for c in repos.boats.list_claims_for_boat(boat_id, status=status)]


def _require_pending_claim(boat_id: uuid.UUID, claim_id: uuid.UUID):
    claim = repos.boats.get_claim(claim_id)
    # The boat_id match is not redundant with the 404: without it a claim
    # against boat A could be resolved by the manager of boat B, who would be
    # authorizing a membership grant on a boat that is none of their business.
    if claim is None or claim.boat_id != boat_id:
        raise HTTPException(404, "Claim not found")
    if claim.status != "pending":
        raise HTTPException(409, "Claim already resolved")
    return claim


def _require_claim_approver(user, boat_id: uuid.UUID):
    """Only the guest boat's owner/admin — in practice its creator — may
    resolve a claim. Approving adds the claimant to ``user_boats``, and boat
    membership is what gates read access to every session recorded on the boat
    (``routers/sessions.py``), so a looser gate here is a data leak, not a UX
    shortcut."""
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")


@router.post("/boats/{boat_id}/claims/{claim_id}/approve")
def approve_claim(boat_id: uuid.UUID, claim_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    boat = _require_boat(boat_id)
    _require_claim_approver(user, boat_id)
    claim = _require_pending_claim(boat_id, claim_id)
    target_id = claim.target_boat_id
    if target_id is not None and not repos.boats.is_member(
            target_id, claim.user_id, roles=["owner", "admin"]):
        raise HTTPException(409, "Claimant no longer manages the target boat")

    # Resolve first: ``boat_claims.boat_id`` is ON DELETE CASCADE, so a merge
    # deletes this very row and there would be nothing left to mark approved.
    if not repos.boats.resolve_claim(claim_id, status="approved", resolved_by=user.id):
        raise HTTPException(409, "Claim already resolved")

    if target_id is None:
        # The demoted-to-visitor party is the creator, not whoever approved: a
        # superadmin can approve without being on the boat at all, and
        # demoting them would rewrite an unrelated membership.
        previous_owner_id = boat.guest_created_by or user.id
        boat_merge.promote_guest_boat(boat_id, new_owner_id=claim.user_id,
                                      previous_owner_id=previous_owner_id)
        return {"ok": True, "merged": None}
    try:
        counts = boat_merge.merge_boat(boat_id, target_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True, "merged": counts}


@router.post("/boats/{boat_id}/claims/{claim_id}/reject")
def reject_claim(boat_id: uuid.UUID, claim_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    _require_claim_approver(user, boat_id)
    _require_pending_claim(boat_id, claim_id)
    if not repos.boats.resolve_claim(claim_id, status="rejected", resolved_by=user.id):
        raise HTTPException(409, "Claim already resolved")
    return {"ok": True}


@router.get("/boats/{boat_id}")
def get_boat(boat_id: uuid.UUID, request: Request):
    return _boat_payload(_require_boat(boat_id), current_user(request))


@router.post("/boats")
def create_boat(body: BoatWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if not body.name:
        raise HTTPException(422, "name is required")
    data = body.model_dump(exclude_unset=True)
    if data.pop("is_guest", False):
        data |= {"is_guest": True, "guest_created_by": user.id}
    boat = repos.boats.create(data)
    repos.boats.add_member(boat.id, user_id=user.id, role="owner")
    return _boat_payload(repos.boats.get(boat.id), user)


@router.patch("/boats/{boat_id}")
def update_boat(boat_id: uuid.UUID, body: BoatWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    return _boat_payload(repos.boats.update(boat_id, body.model_dump(exclude_unset=True)), user)


@router.delete("/boats/{boat_id}")
def delete_boat(boat_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id, owner_only=True):
        raise HTTPException(403, "Boat owner required")
    repos.boats.delete(boat_id)
    return {"ok": True}


# --- members (user_boats) ----------------------------------------------------

@router.get("/boats/{boat_id}/members")
def list_members(boat_id: uuid.UUID, request: Request):
    user = require_user(request)
    _require_boat(boat_id)
    if not (user.is_superadmin or repos.boats.is_member(boat_id, user.id)):
        raise HTTPException(403, "Boat members only")
    return [with_user(m.to_dict(), m.user_id) for m in repos.boats.list_members(boat_id)]


@router.post("/boats/{boat_id}/members")
def add_member(boat_id: uuid.UUID, body: BoatMemberModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    if repos.users.get_by_id(body.user_id) is None:
        raise HTTPException(404, "User not found")
    if not repos.boats.add_member(boat_id, user_id=body.user_id, role=body.role,
                                  default_sailing_role=body.default_sailing_role):
        raise HTTPException(409, "Already a member")
    return {"ok": True}


@router.patch("/boats/{boat_id}/members/{user_id}")
def set_member_role(boat_id: uuid.UUID, user_id: uuid.UUID,
                    body: BoatMemberRoleModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    # Role changes are the owner's prerogative (matrix: "boat:owner cambia ruolo").
    if not _is_manager(user, boat_id, owner_only=True):
        raise HTTPException(403, "Boat owner required")
    if body.role is None and body.default_sailing_role is None:
        raise HTTPException(422, "role or default_sailing_role required")
    if body.role is not None and body.role != "owner":
        member = repos.boats.get_member(boat_id, user_id)
        if member is not None and member.role == "owner" and repos.boats.count_owners(boat_id) <= 1:
            raise HTTPException(409, "Boat must have at least one owner")
    if not repos.boats.set_member_role(boat_id, user_id, role=body.role,
                                       default_sailing_role=body.default_sailing_role):
        raise HTTPException(404, "Member not found")
    return {"ok": True}


@router.delete("/boats/{boat_id}/members/{user_id}")
def remove_member(boat_id: uuid.UUID, user_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if user.id != user_id and not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required (or leave yourself)")
    member = repos.boats.get_member(boat_id, user_id)
    if member is not None and member.role == "owner" and repos.boats.count_owners(boat_id) <= 1:
        raise HTTPException(409, "Cannot remove the boat's only owner")
    if not repos.boats.remove_member(boat_id, user_id):
        raise HTTPException(404, "Member not found")
    return {"ok": True}


# --- notebook (boat_notes) --------------------------------------------------

@router.get("/boats/{boat_id}/notes")
def list_notes(boat_id: uuid.UUID, request: Request):
    user = require_user(request)
    _require_boat(boat_id)
    if not (user.is_superadmin or repos.boats.is_member(boat_id, user.id)):
        raise HTTPException(403, "Boat members only")
    return [n.to_dict() for n in repos.boats.list_notes(boat_id)]


@router.post("/boats/{boat_id}/notes")
def create_note(boat_id: uuid.UUID, body: BoatNoteCreateModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    if not body.title.strip() or not body.body:
        raise HTTPException(422, "title and body are required")
    return repos.boats.add_note(boat_id, body.title, body.body).to_dict()


@router.patch("/boats/{boat_id}/notes/order")
def reorder_notes(boat_id: uuid.UUID, body: BoatNoteOrderModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    if not repos.boats.reorder_notes(boat_id, body.note_ids):
        raise HTTPException(422, "note_ids must list exactly this boat's notes")
    return [n.to_dict() for n in repos.boats.list_notes(boat_id)]


@router.patch("/boats/{boat_id}/notes/{note_id}")
def update_note(boat_id: uuid.UUID, note_id: uuid.UUID, body: BoatNoteUpdateModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    if repos.boats.get_note(boat_id, note_id) is None:
        raise HTTPException(404, "Note not found")
    changes = body.model_dump(exclude_unset=True)
    # Both columns are NOT NULL, so an explicit null is as invalid as a blank.
    if any(not (changes[f] or "").strip() for f in ("title", "body") if f in changes):
        raise HTTPException(422, "title and body are required")
    return repos.boats.update_note(note_id, changes).to_dict()


@router.delete("/boats/{boat_id}/notes/{note_id}")
def delete_note(boat_id: uuid.UUID, note_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    if not repos.boats.remove_note(boat_id, note_id):
        raise HTTPException(404, "Note not found")
    return {"ok": True}


@router.get("/boats/{boat_id}/session-notes")
def list_session_notes(boat_id: uuid.UUID, request: Request,
                       limit: int = Query(50, le=200, gt=0),
                       offset: int = Query(0, ge=0),
                       q: Optional[str] = None):
    """The boat's per-outing crew notes, newest first — the logbook companion
    to the notebook above, and a different audience from it. ``q``, if given,
    narrows to notes containing it (case-insensitive).

    Two gates, both required: boat membership to enumerate at all, then
    ``session_notes_visible_to`` per session for the content — a boat visitor
    who did not sail an outing must not read its notes unless ``notes_shared``.

    That per-item filter runs after the SQL ``limit``, so a page may hold fewer
    than ``limit`` items without meaning the list ended; topping it back up
    would leak how many rows the caller cannot see. The frontend's infinite
    scroll follows the same "short page = end" convention as the diario feed
    (``useDiaryFeed``), accepting that same imprecision for consistency.
    """
    user = require_user(request)
    _require_boat(boat_id)
    if not (user.is_superadmin or repos.boats.is_member(boat_id, user.id)):
        raise HTTPException(403, "Boat members only")
    return [
        {
            "session_id": s.id,
            "activity_id": s.activity_id,
            "started_at": s.started_at,
            "notes": s.notes,
            "notes_shared": s.notes_shared,
        }
        for s in repos.sessions.list_with_notes_for_boat(boat_id, limit=limit, offset=offset, q=q)
        if session_notes_visible_to(s, user)
    ]


# --- media: photos + documents ------------------------------------------------

@router.post("/boats/{boat_id}/photos")
def create_photo(boat_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    payload = media.create_image_upload(user.id)
    repos.boats.add_photo(boat_id, payload["image_id"])
    return payload


@router.post("/boats/{boat_id}/photos/{image_id}/confirm")
def confirm_photo(boat_id: uuid.UUID, image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    if repos.boats.get_photo(boat_id, image_id) is None:
        raise HTTPException(404, "Photo not found")
    if not media.confirm_image(image_id):
        raise HTTPException(409, "Image not uploaded yet")
    return {"ok": True}


@router.delete("/boats/{boat_id}/photos/{image_id}")
def delete_photo(boat_id: uuid.UUID, image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    if not repos.boats.remove_photo(boat_id, image_id):
        raise HTTPException(404, "Photo not found")
    media.delete_image(image_id, user.id)
    return {"ok": True}


def _document_upload(boat_id: uuid.UUID, field: str, request: Request) -> dict:
    verify_csrf(request)
    user = require_user(request)
    _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    payload = media.create_file_upload(user.id, content_type="application/pdf")
    repos.boats.update(boat_id, {field: payload["file_id"]})
    return payload


def _document_delete(boat_id: uuid.UUID, field: str, request: Request) -> dict:
    verify_csrf(request)
    user = require_user(request)
    boat = _require_boat(boat_id)
    if not _is_manager(user, boat_id):
        raise HTTPException(403, "Boat owner/admin required")
    file_id = getattr(boat, field)
    repos.boats.update(boat_id, {field: None})
    if file_id is not None:
        media.delete_file(file_id, user.id)
    return {"ok": True}


@router.post("/boats/{boat_id}/cert")
def upload_cert(boat_id: uuid.UUID, request: Request):
    return _document_upload(boat_id, "cert_id", request)


@router.delete("/boats/{boat_id}/cert")
def delete_cert(boat_id: uuid.UUID, request: Request):
    return _document_delete(boat_id, "cert_id", request)


@router.post("/boats/{boat_id}/mbsa")
def upload_mbsa(boat_id: uuid.UUID, request: Request):
    return _document_upload(boat_id, "mbsa_id", request)


@router.delete("/boats/{boat_id}/mbsa")
def delete_mbsa(boat_id: uuid.UUID, request: Request):
    return _document_delete(boat_id, "mbsa_id", request)
