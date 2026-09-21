"""Media helpers: presigned upload/download of ``images``/``files`` rows.

Media has no standalone CRUD (docs/api-project.md, "Media") — parent routers
call these after their own permission check. Flow: create row (status=
uploaded) → client PUTs to the returned ref → parent's confirm endpoint flips
status to processed. Readers embed ``download_ref`` and skip deleted rows.
"""

import uuid
from typing import Optional

from ..repositories import get_repos
from ..storage import get_blob_store

UPLOAD_URL_EXPIRY_S = 3600


def create_image_upload(user_id: uuid.UUID, *, content_type: str = "image/jpeg") -> dict:
    repos = get_repos()
    image = repos.media.create_image(created_by=user_id)
    ref = f"media/images/{image.id}"
    repos.media.update_image(image.id, {"ref": ref})
    url = get_blob_store().upload_ref(ref, content_type=content_type,
                                      expiry=UPLOAD_URL_EXPIRY_S)
    return {"image_id": image.id, "upload_url": url}


def create_file_upload(user_id: uuid.UUID, *,
                       content_type: str = "application/octet-stream") -> dict:
    repos = get_repos()
    file = repos.media.create_file(created_by=user_id)
    ref = f"media/files/{file.id}"
    repos.media.update_file(file.id, {"ref": ref})
    url = get_blob_store().upload_ref(ref, content_type=content_type,
                                      expiry=UPLOAD_URL_EXPIRY_S)
    return {"file_id": file.id, "upload_url": url}


def register_processed_image(ref: str) -> Optional[uuid.UUID]:
    """Register an image a worker already wrote directly to storage (system
    callbacks, e.g. session track thumbnails) — no presigned-upload/confirm
    dance, since the object is already sitting at `ref`. Returns None (and
    creates no row) if the object isn't actually there."""
    if not get_blob_store().exists(ref):
        return None
    repos = get_repos()
    image = repos.media.create_image(created_by=None)
    repos.media.update_image(image.id, {"ref": ref, "status": "processed"})
    return image.id


def confirm_image(image_id: uuid.UUID) -> bool:
    """Flip to processed once the client reports the PUT done (and the object
    actually exists)."""
    repos = get_repos()
    image = repos.media.get_image(image_id)
    if image is None or image.status == "deleted":
        return False
    if not get_blob_store().exists(image.ref):
        return False
    repos.media.update_image(image_id, {"status": "processed"})
    return True


def confirm_file(file_id: uuid.UUID) -> bool:
    repos = get_repos()
    file = repos.media.get_file(file_id)
    if file is None or file.status == "deleted":
        return False
    if not get_blob_store().exists(file.ref):
        return False
    repos.media.update_file(file_id, {"status": "processed"})
    return True


def delete_image(image_id: uuid.UUID, deleted_by: Optional[uuid.UUID],
                 keep_blob: bool = False) -> bool:
    """``keep_blob``: skip deleting the underlying object. Needed when this
    row's ``ref`` is a fixed, reused key (e.g. worker-rendered thumbnails
    like ``{prefix}thumbnail.png``, always overwritten in place rather than
    given a fresh key per render) and a *newer* image row already points at
    that same key — deleting the blob here would delete the file the newer
    row is supposed to serve, not some orphaned predecessor."""
    repos = get_repos()
    image = repos.media.get_image(image_id)
    if image is None:
        return False
    repos.media.soft_delete_image(image_id, deleted_by)
    if keep_blob:
        return True
    try:
        get_blob_store().delete(image.ref)
    except Exception:
        pass  # row is the source of truth; a stray blob is harmless
    return True


def delete_file(file_id: uuid.UUID, deleted_by: Optional[uuid.UUID]) -> bool:
    repos = get_repos()
    file = repos.media.get_file(file_id)
    if file is None:
        return False
    repos.media.soft_delete_file(file_id, deleted_by)
    try:
        get_blob_store().delete(file.ref)
    except Exception:
        pass
    return True


def image_ref(image) -> Optional[dict]:
    """Same wire shape as ``image_payload``, from an already-fetched
    ``ImageORM`` row. Used where the caller already joined the image (e.g.
    ``photo_covers``) so a second per-row lookup isn't needed."""
    if image is None:
        return None
    return {"image_id": image.id, "url": get_blob_store().download_ref(image.ref)}


def image_payload(image_id: Optional[uuid.UUID]) -> Optional[dict]:
    """Embeddable read shape: id + browser-fetchable URL (None if missing or
    deleted)."""
    if image_id is None:
        return None
    image = get_repos().media.get_image(image_id)
    if image is None or image.status == "deleted":
        return None
    return image_ref(image)


def file_payload(file_id: Optional[uuid.UUID]) -> Optional[dict]:
    if file_id is None:
        return None
    file = get_repos().media.get_file(file_id)
    if file is None or file.status == "deleted":
        return None
    return {"file_id": file.id, "url": get_blob_store().download_ref(file.ref)}


def session_thumbnail_payload(session, *, covers: Optional[dict] = None) -> dict:
    """Session dict + embedded track-preview thumbnail
    (``session_analysis.thumbnail_image_id``) plus the photo ``cover_photo``/
    ``photo_count`` — shared by ``/sessions``, ``/activities/{id}/sessions``
    and the single-session ``GET /sessions/{id}`` so all three show the same
    preview and don't drift into different shapes for the same row.

    ``covers`` is the batch result of ``repos.sessions.photo_covers()`` for a
    whole page of sessions — a list endpoint must pass it in to avoid one
    photo-cover query per row; omitted, it resolves for this one session."""
    d = session.to_dict()
    analysis = get_repos().sessions.get_analysis(session.id)
    d["thumbnail"] = image_payload(analysis.thumbnail_image_id if analysis else None)
    if covers is None:
        covers = get_repos().sessions.photo_covers([session.id])
    cover_image, count = covers.get(session.id, (None, 0))
    d["cover_photo"] = image_ref(cover_image)
    d["photo_count"] = count
    return d


def session_photo_payload(link, image=None, *, users_by_id: Optional[dict] = None) -> Optional[dict]:
    """Attributed photo row for ``GET /sessions/{id}/photos`` (and the
    activity-wide gallery, which adds ``session_id``/``boat`` on top):
    ``image_payload``'s ``{image_id, url}`` — kept verbatim since older
    native OTA bundles read those two keys — plus who added it and when. A
    session is routinely co-owned by two crew who recorded the same outing,
    so a gallery needs to attribute each shot rather than presenting them
    all as one person's.

    ``image`` is the already-joined ``ImageORM`` row (see
    ``list_photos_with_images``); without it the image is fetched per photo,
    which is one query per photograph in a gallery. ``users_by_id`` is a
    caller-owned uploader cache for the same reason: a gallery is usually
    many photos by a handful of people, and ``user_summary`` costs a user
    row plus a profile-image lookup each time."""
    from ..routers._common import user_summary  # local: avoids an import cycle

    base = image_ref(image) if image is not None else image_payload(link.image_id)
    if base is None:
        return None
    uploader = None
    if link.created_by is not None:
        if users_by_id is None:
            uploader = user_summary(link.created_by)
        else:
            if link.created_by not in users_by_id:
                users_by_id[link.created_by] = user_summary(link.created_by)
            uploader = users_by_id[link.created_by]
    return base | {
        "created_at": link.created_at,
        "created_by": link.created_by,
        "user": uploader,
    }


def activity_photos_payload(activity_id: uuid.UUID) -> list[dict]:
    """Every photo across the activity's sessions, oldest first, each row
    carrying ``session_id``/``boat`` on top of ``session_photo_payload``'s
    shape — the aggregation behind ``GET /activities/{id}/photos``. Boats are
    looked up once per distinct boat, not once per photo."""
    repos = get_repos()
    boats_by_id: dict = {}
    users_by_id: dict = {}
    out = []
    for link, image, boat_id in repos.sessions.list_photos_for_activity(activity_id):
        row = session_photo_payload(link, image, users_by_id=users_by_id)
        if row is None:
            continue
        if boat_id not in boats_by_id:
            boat = repos.boats.get(boat_id)
            boats_by_id[boat_id] = (
                {"id": boat.id, "name": boat.name, "sail_number": boat.sail_number}
                if boat else None
            )
        row["session_id"] = link.session_id
        row["boat"] = boats_by_id[boat_id]
        out.append(row)
    return out
