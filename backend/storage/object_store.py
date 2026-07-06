"""S3 / MinIO-backed ``BlobStore`` implementation.

Both AWS S3 and a self-hosted MinIO are the same boto3 client; MinIO differs
only by ``endpoint_url`` + path-style addressing (MinIO does not serve
virtual-host-style buckets without DNS wildcard config). Credentials come from
the standard AWS env vars (set to the MinIO root user/password in compose).
"""

import hashlib
import hmac
import json
import os
import time
from typing import Any, Iterator, Optional, Tuple

from .base import BlobStore, BlobNotFound

# boto3 is imported lazily (inside the functions) so importing this package
# does not require boto3 to be installed until a call actually needs it.


def _upload_secret() -> str:
    secret = os.environ.get("SAILFRAMES_JWT_SECRET") or os.environ.get("SAILFRAMES_HOOK_TOKEN")
    if not secret:
        raise RuntimeError("SAILFRAMES_JWT_SECRET must be set to sign upload URLs")
    return secret


def sign_upload(key: str, expires: int) -> str:
    """HMAC token that makes the MinIO proxy PUT URL self-authorizing (the
    proxy-path equivalent of an S3 presigned URL)."""
    msg = f"{key}:{expires}".encode()
    return hmac.new(_upload_secret().encode(), msg, hashlib.sha256).hexdigest()


def verify_upload_token(key: str, expires: int, token: str) -> bool:
    if expires < int(time.time()):
        return False
    return hmac.compare_digest(sign_upload(key, expires), token)


def make_s3_client(endpoint: Optional[str] = None):
    """Return a boto3 S3 client pointed at AWS S3 or MinIO.

    Kept as a module-level function (and re-exported from ``storage``) for
    backward compatibility with ``from .storage import make_s3_client``.
    """
    import boto3
    from botocore.config import Config

    endpoint = endpoint if endpoint is not None else os.environ.get("SAILFRAMES_S3_ENDPOINT")
    if not endpoint:
        return boto3.client("s3")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        config=Config(s3={"addressing_style": "path"}),
    )


def _is_not_found(exc: Exception) -> bool:
    from botocore.exceptions import ClientError

    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        return code in ("404", "NoSuchKey", "NotFound", "NoSuchBucket")
    return False


class ObjectBlobStore(BlobStore):
    """AWS S3 or MinIO. ``endpoint`` set => MinIO.

    Two clients when self-hosted: ``_s3`` (internal ``endpoint``, e.g.
    ``http://minio:9000``) for every server-side operation, and ``_s3_public``
    (``SAILFRAMES_S3_PUBLIC_ENDPOINT``) used ONLY to sign presigned URLs, so
    the browser gets a real presigned PUT/GET straight to MinIO instead of
    shovelling bytes through the backend+nginx proxy (which forced a memory
    buffer and a hand-picked size cap). Falls back to the proxy routes
    (``routers/uploads.py`` / ``routers/download.py``) when no public
    endpoint is configured, e.g. a deployment that hasn't exposed MinIO
    publicly yet."""

    def __init__(self, bucket: str, endpoint: Optional[str] = None):
        self.bucket = bucket
        self.endpoint = endpoint
        self._s3 = make_s3_client(endpoint)
        public_endpoint = os.environ.get("SAILFRAMES_S3_PUBLIC_ENDPOINT")
        self._s3_public = make_s3_client(public_endpoint) if public_endpoint else None

    def get_bytes(self, key: str) -> bytes:
        try:
            resp = self._s3.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                raise BlobNotFound(key)
            raise
        return resp["Body"].read()

    def get_json(self, key: str) -> Any:
        return json.loads(self.get_bytes(key))

    def put_bytes(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
        if isinstance(body, str):
            body = body.encode()
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)

    def put_json(self, key: str, data: Any) -> None:
        self.put_bytes(key, json.dumps(data, indent=2).encode(), "application/json")

    def exists(self, key: str) -> bool:
        return self.head(key) is not None

    def head(self, key: str) -> Optional[dict]:
        try:
            resp = self._s3.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise
        return {
            "size": resp["ContentLength"],
            "last_modified": resp["LastModified"],
            "content_type": resp.get("ContentType", "application/octet-stream"),
        }

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str) -> int:
        deleted = 0
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = page.get("Contents", [])
            if objects:
                self._s3.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": o["Key"]} for o in objects]},
                )
                deleted += len(objects)
        return deleted

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
        except Exception as exc:
            if _is_not_found(exc):
                return keys
            raise
        return keys

    def list_with_metadata(self, prefix: str) -> list[dict]:
        results: list[dict] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    results.append({
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                    })
        except Exception as exc:
            if _is_not_found(exc):
                return results
            raise
        return results

    def open_stream(self, key: str) -> Tuple[Iterator[bytes], str, Optional[Any]]:
        try:
            obj = self._s3.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                raise BlobNotFound(key)
            raise
        content_type = obj.get("ContentType") or "application/octet-stream"
        return obj["Body"].iter_chunks(), content_type, obj.get("LastModified")

    def download_ref(self, key: str, expiry: int = 3600) -> str:
        # MinIO's internal endpoint (minio:9000) is unreachable from the
        # browser. If a public endpoint is configured, sign a real presigned
        # URL against it — same bytes-never-touch-the-app-tier path as AWS.
        # Otherwise fall back to the API download proxy (routers/download.py).
        if self.endpoint and self._s3_public is None:
            return f"/api/download/{key}"
        client = self._s3_public or self._s3
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expiry,
        )

    def upload_ref(self, key: str, content_type: str = "application/octet-stream", expiry: int = 3600) -> str:
        # Same reasoning as download_ref. Without a public endpoint, fall
        # back to the HMAC-signed proxy PUT (routers/uploads.py) — carries
        # its own authorization, exactly like a presigned S3 URL (devices
        # send no auth header on the PUT — docs/device-protocol.md §4.1).
        if self.endpoint and self._s3_public is None:
            expires = int(time.time()) + expiry
            token = sign_upload(key, expires)
            return f"/api/uploads/{key}?expires={expires}&token={token}"
        client = self._s3_public or self._s3
        return client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expiry,
        )
