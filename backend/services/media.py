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


def delete_image(image_id: uuid.UUID, deleted_by: Optional[uuid.UUID]) -> bool:
    repos = get_repos()
    image = repos.media.get_image(image_id)
    if image is None:
        return False
    repos.media.soft_delete_image(image_id, deleted_by)
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


def image_payload(image_id: Optional[uuid.UUID]) -> Optional[dict]:
    """Embeddable read shape: id + browser-fetchable URL (None if missing or
    deleted)."""
    if image_id is None:
        return None
    image = get_repos().media.get_image(image_id)
    if image is None or image.status == "deleted":
        return None
    return {"image_id": image.id, "url": get_blob_store().download_ref(image.ref)}


def file_payload(file_id: Optional[uuid.UUID]) -> Optional[dict]:
    if file_id is None:
        return None
    file = get_repos().media.get_file(file_id)
    if file is None or file.status == "deleted":
        return None
    return {"file_id": file.id, "url": get_blob_store().download_ref(file.ref)}
