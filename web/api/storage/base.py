"""Storage-backend-agnostic blob interface for SailFrames.

A ``BlobStore`` is the single abstraction every part of the web API uses to
read/write objects, replacing the ad-hoc ``if LOCAL_DATA_DIR``/S3 branches that
used to live in main.py, race.py and ingest.py. Implementations:

- ``ObjectBlobStore`` — AWS S3 *or* MinIO (path-style), in object_store.py
- ``LocalBlobStore`` — local filesystem, in local_store.py

Selected at startup by ``get_blob_store()`` (see ``__init__.py``) based on
``SAILFRAMES_STORAGE_BACKEND`` (s3 | minio | local), falling back to the legacy
``SAILFRAMES_LOCAL_DATA`` / ``SAILFRAMES_S3_ENDPOINT`` vars.
"""

from abc import ABC, abstractmethod
from typing import Any, Iterator, Optional, Tuple


class BlobNotFound(Exception):
    """Raised when a key does not exist. Callers map this to their own
    semantics (HTTP 404, empty dict, etc.) — the store never raises HTTP."""


class BlobStore(ABC):
    """Key/value object storage. Keys are S3-style paths (``raw/E1/...``)."""

    # --- bytes / json ---

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        """Return object bytes. Raises ``BlobNotFound`` if absent."""

    @abstractmethod
    def put_bytes(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
        ...

    @abstractmethod
    def get_json(self, key: str) -> Any:
        """Return parsed JSON. Raises ``BlobNotFound`` if absent."""

    @abstractmethod
    def put_json(self, key: str, data: Any) -> None:
        ...

    # --- existence / metadata ---

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def head(self, key: str) -> Optional[dict]:
        """``{size, last_modified, content_type}`` or ``None`` if absent.
        ``last_modified`` is a ``datetime``."""

    # --- delete ---

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int:
        """Delete everything under ``prefix``; return count of objects removed."""

    # --- listing ---

    @abstractmethod
    def list_keys(self, prefix: str) -> list[str]:
        ...

    @abstractmethod
    def list_with_metadata(self, prefix: str) -> list[dict]:
        """List of ``{key, size, last_modified}`` (last_modified is an ISO str)."""

    # --- streaming / download indirection ---

    @abstractmethod
    def open_stream(self, key: str) -> Tuple[Iterator[bytes], str, Optional[Any]]:
        """``(chunk_iterator, content_type, last_modified)``. Raises
        ``BlobNotFound`` if absent. Used by the download/fleet proxies."""

    @abstractmethod
    def download_ref(self, key: str, expiry: int = 3600) -> str:
        """A URL/path the browser can fetch the object from: an S3 presigned
        URL (AWS), or an API proxy path (MinIO / local)."""
