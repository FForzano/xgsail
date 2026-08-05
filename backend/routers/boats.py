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
from ..schemas import (
    BoatClassWriteModel,
    BoatMemberModel,
    BoatMemberRoleModel,
    BoatNoteCreateModel,
    BoatNoteOrderModel,
    BoatNoteUpdateModel,
    BoatWriteModel,
)
from ..services import media
from ._common import repos, with_user

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


@router.get("/boats/{boat_id}")
def get_boat(boat_id: uuid.UUID, request: Request):
    return _boat_payload(_require_boat(boat_id), current_user(request))


@router.post("/boats")
def create_boat(body: BoatWriteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if not body.name:
        raise HTTPException(422, "name is required")
    boat = repos.boats.create(body.model_dump(exclude_unset=True))
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
    if not body.title.strip() or not body.body.strip():
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
                       offset: int = Query(0, ge=0)):
    """The boat's per-outing crew notes, newest first — the logbook companion
    to the notebook above, and a different audience from it.

    Two gates, both required: boat membership to enumerate at all, then
    ``session_notes_visible_to`` per session for the content — a boat visitor
    who did not sail an outing must not read its notes unless ``notes_shared``.

    That per-item filter runs after the SQL ``limit``, so a page may hold fewer
    than ``limit`` items without meaning the list ended; topping it back up
    would leak how many rows the caller cannot see.
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
        for s in repos.sessions.list_with_notes_for_boat(boat_id, limit=limit, offset=offset)
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
