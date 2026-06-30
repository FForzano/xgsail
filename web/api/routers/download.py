"""Object download proxies (stream bytes out of the blob store).

Two routes with identical behavior, kept separate for backward compatibility:

- ``/api/download/{key}``    — the target produced by ``BlobStore.download_ref``
  for the MinIO backend (keeps MinIO's internal endpoint private; replaces S3
  presigned URLs).
- ``/api/e1/download/{key}`` — the download target for the ``local`` backend;
  harmless on other backends.

Both stream via ``blob.open_stream``. Consolidated here so the streaming logic
lives in one place; the duplicate path is a known follow-up (collapsing to a
single URL would be a breaking change for callers and is out of scope).
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ._common import blob
from ..storage import BlobNotFound

router = APIRouter(tags=["download"])


def _stream(key: str) -> StreamingResponse:
    try:
        chunks, content_type, _ = blob.open_stream(key)
    except BlobNotFound:
        raise HTTPException(404, f"Object not found: {key}")
    filename = key.rsplit("/", 1)[-1]
    return StreamingResponse(
        chunks,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/api/download/{key:path}")
def download_object(key: str):
    """Stream an object out of the blob store (keeps MinIO/local private)."""
    return _stream(key)


@router.get("/api/e1/download/{key:path}")
def download_e1_file(key: str):
    """Stream an object out of the blob store (local-backend download target)."""
    return _stream(key)
