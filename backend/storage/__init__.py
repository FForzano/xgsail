"""Blob storage factory for SailFrames.

``get_blob_store()`` returns a process-wide ``BlobStore`` backed by object
storage: AWS S3, or a MinIO/S3-compatible endpoint when ``SAILFRAMES_S3_ENDPOINT``
is set. ``make_s3_client`` is re-exported for callers that need the raw client.
"""

import os

from .base import BlobStore, BlobNotFound
from .object_store import ObjectBlobStore, make_s3_client, verify_upload_token

_blob_store: BlobStore | None = None


def build_blob_store() -> BlobStore:
    # S3 and MinIO share the same client; MinIO just carries an endpoint URL.
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
    "make_s3_client",
    "verify_upload_token",
    "get_blob_store",
    "build_blob_store",
]
