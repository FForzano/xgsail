"""MinIO proxy PUT target (``PUT /api/uploads/{key}``).

On self-hosted MinIO, ``BlobStore.upload_ref`` returns this route instead of a
presigned S3 URL (the MinIO host isn't reachable from outside the compose
network). The URL carries its own authorization — an HMAC token minted by
``upload_ref`` — so the PUT needs no cookie or DeviceKey header, exactly like
a presigned URL (docs/device-protocol.md §4.1). Key scope is limited to the
prefixes ``upload_ref`` is ever called with.
"""

from fastapi import APIRouter, HTTPException, Request

from ..storage import verify_upload_token
from ._common import blob

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

_ALLOWED_PREFIXES = ("raw/uploads/", "raw/imports/", "media/images/", "media/files/")


@router.put("/{key:path}")
async def upload_object(key: str, request: Request, expires: int = 0, token: str = ""):
    if not key.startswith(_ALLOWED_PREFIXES):
        raise HTTPException(403, "Key outside the allowed upload scopes")
    if not token or not verify_upload_token(key, expires, token):
        raise HTTPException(403, "Invalid or expired upload URL")
    body = await request.body()
    if not body:
        raise HTTPException(422, "Empty body")
    content_type = request.headers.get("content-type", "application/octet-stream")
    blob.put_bytes(key, body, content_type=content_type)
    return {"ok": True, "key": key, "size": len(body)}
