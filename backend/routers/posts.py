"""Feed post endpoints (``/api/posts``) — generic across club/group owners.

Matrix: read = same visibility as the owner (club: always public; group:
``can_read_group``); create/delete = ``club_post.manage`` (RBAC scoped) for
club posts, group owner/admin (``is_group_manager``) for group posts. Edit
(body only) is author-only, regardless of manage permission — a manager can
delete someone else's post but not rewrite it.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..auth import current_user, require_permission, require_user, verify_csrf
from ..schemas import PostCreateModel, PostUpdateModel
from ..services import media
from ._common import can_read_group, is_group_manager, repos, user_summary

router = APIRouter(prefix="/api/posts", tags=["posts"])


def _require_owner(owner_type: str, owner_id: uuid.UUID):
    if owner_type == "club":
        owner = repos.clubs.get(owner_id)
    elif owner_type == "group":
        owner = repos.groups.get(owner_id)
        if owner is not None and owner.deleted_at is not None:
            owner = None
    else:
        raise HTTPException(422, "owner_type must be 'club' or 'group'")
    if owner is None:
        raise HTTPException(404, f"{owner_type.capitalize()} not found")
    return owner


def _can_read(owner_type: str, owner, user) -> bool:
    if owner_type == "club":
        return True
    return can_read_group(owner, user)


def _can_manage(owner_type: str, owner_id: uuid.UUID, request: Request, *, activity=None, regatta=None) -> None:
    """Raises 403 if the caller may not create/delete posts for this owner.

    A post tied to an event (``activity``/``regatta``) is gated by whoever
    can already manage *that event*, not the generic ``club_post.manage`` —
    announcing a regatta/uscita is part of organizing it, not a separate
    permission.
    """
    if regatta is not None:
        require_permission(request, "regatta.manage", club_id=owner_id)
        return
    if activity is not None:
        if activity.club_id is not None:
            require_permission(request, "activity.manage", club_id=owner_id)
        else:
            user = require_user(request)
            if not is_group_manager(user, owner_id):
                raise HTTPException(403, "Group owner/admin required")
        return
    if owner_type == "club":
        require_permission(request, "club_post.manage", club_id=owner_id)
    else:
        user = require_user(request)
        if not is_group_manager(user, owner_id):
            raise HTTPException(403, "Group owner/admin required")


def _event_ref(post) -> dict | None:
    """The activity/regatta a post announces, shaped for the frontend to
    render a Facebook-share-style nested card (title falls back to the
    activity type on the client, same as the diario event cards — see
    ``EventRow.tsx`` — and the image/description mirror what that card
    shows too)."""
    if post.activity_id is not None:
        a = repos.activities.get(post.activity_id)
        if a is None:
            return None
        return {
            "kind": "activity", "id": a.id, "title": a.name, "type": a.type, "date": a.started_at,
            "description": a.description, "image": media.image_payload(a.thumbnail_image_id),
        }
    if post.regatta_id is not None:
        r = repos.regattas.get(post.regatta_id)
        if r is None:
            return None
        return {
            "kind": "regatta", "id": r.id, "title": r.name, "date": r.start_date,
            "description": r.description, "image": media.image_payload(r.image_id),
        }
    return None


def _post_payload(post) -> dict:
    d = post.to_dict()
    d["author"] = user_summary(post.author_id) if post.author_id else None
    d["images"] = [
        img for pi in repos.posts.list_images(post.id)
        if (img := media.image_payload(pi.image_id)) is not None
    ]
    d["event"] = _event_ref(post)
    return d


@router.get("")
def list_posts(owner_type: str, owner_id: uuid.UUID, request: Request):
    owner = _require_owner(owner_type, owner_id)
    user = current_user(request)
    if not _can_read(owner_type, owner, user):
        raise HTTPException(404, f"{owner_type.capitalize()} not found")
    return [_post_payload(p) for p in repos.posts.list_for_owner(owner_type, owner_id)]


def _resolve_event(body: PostCreateModel):
    """Validates the optional activity/regatta link belongs to the post's
    owner, returning the loaded ORM row(s) for `_can_manage` to gate on."""
    if body.activity_id is not None and body.regatta_id is not None:
        raise HTTPException(422, "activity_id and regatta_id are mutually exclusive")
    if body.activity_id is not None:
        activity = repos.activities.get(body.activity_id)
        owned = activity is not None and (
            activity.club_id == body.owner_id if body.owner_type == "club"
            else activity.group_id == body.owner_id
        )
        if not owned:
            raise HTTPException(404, "Activity not found")
        return activity, None
    if body.regatta_id is not None:
        if body.owner_type != "club":
            raise HTTPException(422, "regatta_id requires owner_type 'club'")
        regatta = repos.regattas.get(body.regatta_id)
        if regatta is None or regatta.club_id != body.owner_id:
            raise HTTPException(404, "Regatta not found")
        return None, regatta
    return None, None


@router.post("")
def create_post(body: PostCreateModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_owner(body.owner_type, body.owner_id)
    activity, regatta = _resolve_event(body)
    _can_manage(body.owner_type, body.owner_id, request, activity=activity, regatta=regatta)
    if not body.body:
        raise HTTPException(422, "body is required")
    post = repos.posts.create({
        "owner_type": body.owner_type,
        "owner_id": body.owner_id,
        "author_id": user.id,
        "body": body.body,
        "activity_id": body.activity_id,
        "regatta_id": body.regatta_id,
    })
    for image_id in body.image_ids:
        repos.posts.add_image(post.id, image_id)
    return _post_payload(post)


@router.patch("/{post_id}")
def update_post(post_id: uuid.UUID, body: PostUpdateModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    post = repos.posts.get(post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    if post.author_id != user.id:
        raise HTTPException(403, "Only the author can edit this post")
    if not body.body:
        raise HTTPException(422, "body is required")
    updated = repos.posts.update(post_id, {"body": body.body, "updated_at": datetime.now(timezone.utc)})
    return _post_payload(updated)


@router.delete("/{post_id}")
def delete_post(post_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    post = repos.posts.get(post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    if post.author_id != user.id:
        _can_manage(post.owner_type, post.owner_id, request)
    repos.posts.delete(post_id)
    return {"ok": True}


# --- image ------------------------------------------------------------------

@router.post("/image")
def upload_post_image(request: Request):
    """The image is uploaded/confirmed before the post exists (unlike a club
    logo, which attaches to an already-created row) — any authenticated user
    may start an upload; the permission check happens at `POST /posts`."""
    verify_csrf(request)
    user = require_user(request)
    return media.create_image_upload(user.id)


@router.post("/image/{image_id}/confirm")
def confirm_post_image(image_id: uuid.UUID, request: Request):
    verify_csrf(request)
    require_user(request)
    if not media.confirm_image(image_id):
        raise HTTPException(409, "Image not uploaded yet")
    return {"ok": True}
