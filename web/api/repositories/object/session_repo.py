"""Object-storage session repository.

Sessions are derived from the per-session ``manifest.json`` files the
processing pipeline writes under ``{DATA_PREFIX}/{device}/{date}/{sid}/``.
"""

from datetime import datetime
from typing import Optional

from ... import domain
from ...storage import BlobStore, BlobNotFound
from ..base import SessionRepo


def _duration(manifest: dict) -> int:
    duration_sec = manifest.get("duration_sec")
    if duration_sec:
        return int(duration_sec)
    start_time = manifest.get("start_time")
    end_time = manifest.get("end_time")
    if start_time and end_time:
        try:
            s = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            e = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            return int((e - s).total_seconds())
        except (ValueError, TypeError):
            return 0
    return 0


def _to_session(manifest: dict, device_id: str, date: str) -> domain.Session:
    # Preserve any extra manifest fields (cameras, etc.) via extra="allow".
    data = {
        **manifest,
        "device_id": device_id,
        "date": date,
        "duration_sec": _duration(manifest),
        "sensors": manifest.get("sensors", []),
        "has_video": manifest.get("has_video", False),
        "has_analysis": manifest.get("has_analysis", False),
    }
    return domain.Session.from_dict(data)


class ObjectSessionRepo(SessionRepo):
    def __init__(self, blob: BlobStore, data_prefix: str):
        self.blob = blob
        self.data_prefix = data_prefix

    def list(self) -> list[domain.Session]:
        sessions = []
        for key in self.blob.list_keys(f"{self.data_prefix}/"):
            if not key.endswith("manifest.json"):
                continue
            try:
                manifest = self.blob.get_json(key)
                parts = key.split("/")
                device_id = parts[1] if len(parts) > 2 else "unknown"
                date = parts[2] if len(parts) > 2 else "unknown"
                sessions.append(_to_session(manifest, device_id, date))
            except Exception:
                continue
        return sessions

    def get(self, device_id: str, date: str) -> Optional[domain.Session]:
        key = f"{self.data_prefix}/{device_id}/{date}/manifest.json"
        try:
            manifest = self.blob.get_json(key)
        except BlobNotFound:
            return None
        return _to_session(manifest, device_id, date)
