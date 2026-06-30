"""Local-filesystem ``BlobStore`` implementation.

Keys map to paths under a single root directory (``SAILFRAMES_LOCAL_DATA``).
Used for offline development and tests; never the production path.
"""

import json
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional, Tuple

from .base import BlobStore, BlobNotFound

_CHUNK = 64 * 1024


def _guess_ct(key: str) -> str:
    ct, _ = mimetypes.guess_type(key)
    return ct or "application/octet-stream"


class LocalBlobStore(BlobStore):
    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key

    def get_bytes(self, key: str) -> bytes:
        p = self._path(key)
        if not p.exists():
            raise BlobNotFound(key)
        return p.read_bytes()

    def get_json(self, key: str) -> Any:
        return json.loads(self.get_bytes(key))

    def put_bytes(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, str):
            body = body.encode()
        p.write_bytes(body)

    def put_json(self, key: str, data: Any) -> None:
        self.put_bytes(key, json.dumps(data, indent=2).encode(), "application/json")

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def head(self, key: str) -> Optional[dict]:
        p = self._path(key)
        if not p.exists():
            return None
        st = p.stat()
        return {
            "size": st.st_size,
            "last_modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
            "content_type": _guess_ct(key),
        }

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def delete_prefix(self, prefix: str) -> int:
        base = self._path(prefix)
        count = 0
        if base.exists():
            for p in base.rglob("*"):
                if p.is_file():
                    p.unlink()
                    count += 1
            shutil.rmtree(base, ignore_errors=True)
        return count

    def list_keys(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        return [str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file()]

    def list_with_metadata(self, prefix: str) -> list[dict]:
        base = self._path(prefix)
        if not base.exists():
            return []
        results: list[dict] = []
        for p in base.rglob("*"):
            if p.is_file():
                st = p.stat()
                results.append({
                    "key": str(p.relative_to(self.root)),
                    "size": st.st_size,
                    "last_modified": datetime.fromtimestamp(st.st_mtime).isoformat() + "Z",
                })
        return results

    def open_stream(self, key: str) -> Tuple[Iterator[bytes], str, Optional[Any]]:
        p = self._path(key)
        if not p.exists():
            raise BlobNotFound(key)

        def _iter() -> Iterator[bytes]:
            with open(p, "rb") as f:
                while True:
                    chunk = f.read(_CHUNK)
                    if not chunk:
                        break
                    yield chunk

        st = p.stat()
        return _iter(), _guess_ct(key), datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)

    def download_ref(self, key: str, expiry: int = 3600) -> str:
        return f"/api/e1/download/{key}"
