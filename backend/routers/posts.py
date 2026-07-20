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


def _can_manage(owner_type: str, owner_id: uuid.UUID, request: Request) -> None:
    """Raises 403 if the caller may not create/delete posts for this owner."""
    if owner_type == "club":
        require_permission(request, "club_post.manage", club_id=owner_id)
    else:
        user = require_user(request)
        if not is_group_manager(user, owner_id):
            raise HTTPException(403, "Group owner/admin required")


def _post_payload(post) -> dict:
    d = post.to_dict()
    d["author"] = user_summary(post.author_id) if post.author_id else None
    d["images"] = [
        img for pi in repos.posts.list_images(post.id)
        if (img := media.image_payload(pi.image_id)) is not None
    ]
    return d


@router.get("")
def list_posts(owner_type: str, owner_id: uuid.UUID, request: Request):
    owner = _require_owner(owner_type, owner_id)
    user = current_user(request)
    if not _can_read(owner_type, owner, user):
        raise HTTPException(404, f"{owner_type.capitalize()} not found")
    return [_post_payload(p) for p in repos.posts.list_for_owner(owner_type, owner_id)]


@router.post("")
def create_post(body: PostCreateModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_owner(body.owner_type, body.owner_id)
    _can_manage(body.owner_type, body.owner_id, request)
    if not body.body.strip():
        raise HTTPException(422, "body is required")
    post = repos.posts.create({
        "owner_type": body.owner_type,
        "owner_id": body.owner_id,
        "author_id": user.id,
        "body": body.body,
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
    if not body.body.strip():
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
