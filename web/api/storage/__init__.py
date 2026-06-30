"""Blob storage factory for SailFrames.

``get_blob_store()`` returns a process-wide ``BlobStore`` selected by
``SAILFRAMES_STORAGE_BACKEND`` (``s3`` | ``minio`` | ``local``). When that var
is unset the backend is *derived* from the legacy vars so existing deployments
keep working unchanged:

- ``SAILFRAMES_LOCAL_DATA`` set  -> ``local``
- ``SAILFRAMES_S3_ENDPOINT`` set -> ``minio``
- otherwise                      -> ``s3``

``make_s3_client`` is re-exported for backward compatibility.
"""

import os

from .base import BlobStore, BlobNotFound
from .object_store import ObjectBlobStore, make_s3_client
from .local_store import LocalBlobStore

_blob_store: BlobStore | None = None


def select_backend() -> str:
    backend = os.environ.get("SAILFRAMES_STORAGE_BACKEND")
    if backend:
        return backend.lower()
    if os.environ.get("SAILFRAMES_LOCAL_DATA"):
        return "local"
    if os.environ.get("SAILFRAMES_S3_ENDPOINT"):
        return "minio"
    return "s3"


def build_blob_store() -> BlobStore:
    backend = select_backend()
    if backend == "local":
        root = os.environ.get("SAILFRAMES_LOCAL_DATA")
        if not root:
            raise RuntimeError(
                "SAILFRAMES_STORAGE_BACKEND=local requires SAILFRAMES_LOCAL_DATA"
            )
        return LocalBlobStore(root)
    # s3 or minio: same client, MinIO just carries an endpoint.
    bucket = os.environ.get("SAILFRAMES_BUCKET", "sailframes-fleet-data-prod")
    endpoint = os.environ.get("SAILFRAMES_S3_ENDPOINT")
    return ObjectBlobStore(bucket, endpoint)


def get_blob_store() -> BlobStore:
    global _blob_store
    if _blob_store is None:
        _blob_store = build_blob_store()
    return _blob_store


__all__ = [
    "BlobStore",
    "BlobNotFound",
    "ObjectBlobStore",
    "LocalBlobStore",
    "make_s3_client",
    "get_blob_store",
    "build_blob_store",
    "select_backend",
]
