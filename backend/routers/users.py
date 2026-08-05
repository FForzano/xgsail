"""User account endpoints (``/api/users``).

Matrix (docs/api-project.md): read/update/delete = self or superadmin; list =
superadmin; delete is always soft (status=deleted). Registration lives in the
auth router. Profile image is parent-mediated media (presign + confirm).
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, Request

from ..auth import hash_password, require_superadmin, require_user, verify_csrf
from ..schemas import UserUpdateModel
from ..services import media
from ._common import repos, user_summary

router = APIRouter(prefix="/api/users", tags=["users"])


def _self_or_superadmin(request: Request, user_id: uuid.UUID):
    user = require_user(request)
    if user.id != user_id and not user.is_superadmin:
        raise HTTPException(403, "Not allowed")
    return user


@router.get("")
def list_users(request: Request):
    require_superadmin(request)
    return [u.to_dict() for u in repos.users.list()]


@router.get("/me")
def get_me(request: Request):
    user = require_user(request)
    d = user.to_dict()
    d["profile_image"] = media.image_payload(user.profile_image_id)
    return d


@router.get("/me/memberships")
def my_memberships(request: Request):
    """All my club/group memberships including pending invites — one call for
    the frontend's invites/notifications strip."""
    user = require_user(request)
    return {
        "clubs": repos.clubs.list_memberships_for_user(user.id),
        "groups": repos.groups.list_memberships_for_user(user.id),
    }


@router.get("/lookup")
def lookup_user(email: str, request: Request):
    """Exact-match user lookup by email — any authenticated user, minimal
    fields only.

    Compatibility surface, not the current path: the web app now finds people
    through ``/users/search``. This stays because already-installed native
    apps run whatever OTA bundle they last pulled, and the older ones still
    call this to invite someone — deleting it 404s their invite flow until
    they update. Removable once no shipped bundle references it."""
    require_user(request)
    found = repos.users.get_by_email(email.strip())
    if found is None or not found.is_active:
        raise HTTPException(404, "User not found")
    return user_summary(found.id)


@router.get("/search")
def search_users(
    request: Request,
    q: str = Query(..., min_length=2),
    limit: int = Query(20, gt=0, le=50),
):
    """Name/email partial-match search for a Facebook-style "pick a person"
    picker — any authenticated user. Deliberately searches *all* active
    users, not just people the caller already shares a club/group/boat
    with: the point is finding someone to invite you don't yet share
    anything with. The ``min_length`` and ``limit`` cap are the only
    anti-enumeration measures (a 1-character query would return a huge
    slice of the instance); the "shared" ranking below is a UX convenience,
    not a permission boundary.

    Deliberately does NOT exclude the caller: this endpoint backs every
    "add a person" picker, including session crew, and nothing auto-adds a
    session's creator as its own crew — excluding self here made it
    impossible to add yourself. The other pickers (boat/club/group members)
    already 409 gracefully on "already a member" if picked anyway.

    ``q`` may still match on email (a caller who knows someone's email but
    not their exact name spelling can find them that way), but the response
    never carries it: unlike the other ``user_summary`` consumers (crew/
    member rosters, already scoped to people who share a club/group/boat),
    this endpoint deliberately surfaces *any* active user to *any*
    authenticated caller — showing email there would hand out an address
    the searcher has no existing relationship to that person to justify.
    """
    user = require_user(request)
    q = q.strip()
    if not q:
        return []
    found = repos.users.search(q, limit=limit)
    related = repos.users.related_user_ids(user.id)
    results = []
    for u in found:
        row = user_summary(u.id)
        row.pop("email", None)
        row["shared"] = u.id in related
        results.append(row)
    results.sort(key=lambda r: not r["shared"])
    return results


@router.get("/{user_id}")
def get_user(user_id: uuid.UUID, request: Request):
    _self_or_superadmin(request, user_id)
    user = repos.users.get_by_id(user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    d = user.to_dict()
    d["profile_image"] = media.image_payload(user.profile_image_id)
    return d


@router.patch("/{user_id}")
def update_user(user_id: uuid.UUID, body: UserUpdateModel, request: Request):
    verify_csrf(request)
    _self_or_superadmin(request, user_id)
    changes = body.model_dump(exclude_unset=True)
    password = changes.pop("password", None)
    if password is not None:
        if len(password) < 8:
            raise HTTPException(422, "Password must be at least 8 characters")
        changes["password_hash"] = hash_password(password)
    updated = repos.users.update(user_id, changes)
    if updated is None:
        raise HTTPException(404, "User not found")
    return updated.to_dict()


@router.delete("/{user_id}")
def delete_user(user_id: uuid.UUID, request: Request):
    verify_csrf(request)
    _self_or_superadmin(request, user_id)
    if not repos.users.soft_delete(user_id):
        raise HTTPException(404, "User not found")
    return {"ok": True}


@router.post("/me/profile-image")
def create_profile_image(request: Request):
    verify_csrf(request)
    user = require_user(request)
    return media.create_image_upload(user.id)


@router.post("/me/profile-image/{image_id}/confirm")
def confirm_profile_image(image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    image = repos.media.get_image(image_id)
    if image is None or image.created_by != user.id:
        raise HTTPException(404, "Image not found")
    if not media.confirm_image(image_id):
        raise HTTPException(409, "Image not uploaded yet")
    repos.users.update(user.id, {"profile_image_id": image_id})
    return {"ok": True, "profile_image": media.image_payload(image_id)}
