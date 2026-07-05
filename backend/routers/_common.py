"""Shared HTTP-layer helpers for the SailFrames router modules.

These wrap the blob store + repository layer with the small conveniences the
endpoints need (JSON load/save, presigned refs, listing, byte formatting).
Centralised here so each router imports one place instead of re-deriving the
helpers (they used to be duplicated between main.py and race.py).

Note the two ``load_json`` variants — they differ on the *missing key* case
and that difference is load-bearing:

- ``load_json_or_404`` raises ``HTTPException(404)`` (used by data/analysis/
  video/leaderboard, where a missing artifact is a real 404).
- ``load_json_or_empty`` returns ``{}`` (used by races, where a missing GPX /
  sensor file degrades gracefully into an empty result).
"""

import os
from datetime import datetime

from fastapi import HTTPException

from ..storage import get_blob_store, BlobNotFound
from ..repositories import get_repos

# Process-wide singletons (both are lazy singletons internally, so importing
# this module from many routers is cheap and shares one instance).
blob = get_blob_store()
repos = get_repos()

DATA_PREFIX = os.environ.get("SAILFRAMES_DATA_PREFIX", "processed")


# --- JSON load/save -------------------------------------------------------

def load_json_or_404(key: str) -> dict:
    """Load JSON from the blob store, raising 404 if the key is missing."""
    try:
        return blob.get_json(key)
    except BlobNotFound:
        raise HTTPException(404, f"Data not found: {key}")


def load_json_or_empty(key: str):
    """Load non-entity JSON (GPX tracks, sensor data), tolerating a missing or
    corrupt object as ``{}`` rather than erroring."""
    try:
        return blob.get_json(key)
    except BlobNotFound:
        return {}
    except Exception:
        return {}


def save_json(key: str, data) -> None:
    """Save non-entity JSON (GPX tracks) to the blob store."""
    blob.put_json(key, data)


# --- Blob listing / refs / deletion --------------------------------------

def list_keys(prefix: str) -> list[str]:
    """List keys under prefix."""
    return blob.list_keys(prefix)


def list_objects_with_metadata(prefix: str) -> list[dict]:
    """List objects with size and last modified metadata."""
    return blob.list_with_metadata(prefix)


def generate_presigned_url(key: str, expiry: int = 3600) -> str:
    """A browser-fetchable reference for a key: presigned URL (AWS) or proxy
    path (MinIO / local). Backend decides; see ``BlobStore.download_ref``."""
    return blob.download_ref(key, expiry)


def delete_prefix(prefix: str) -> int:
    """Delete all objects under a prefix. Returns count of deleted objects."""
    return blob.delete_prefix(prefix)


# --- Wire helpers -----------------------------------------------------------

def user_summary(user_id) -> dict | None:
    """Minimal public user shape embedded in member/crew rows (boats, clubs,
    groups) so rosters can render names without extra requests."""
    u = repos.users.get_by_id(user_id)
    if u is None:
        return None
    return {"id": u.id, "first_name": u.first_name,
            "last_name": u.last_name, "email": u.email}


def with_user(row_dict: dict, user_id) -> dict:
    """Attach ``user_id`` + embedded ``user`` summary to a membership row."""
    return row_dict | {"user_id": user_id, "user": user_summary(user_id)}


# --- Misc -----------------------------------------------------------------

def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat() + "Z"


def detect_file_type(filename: str) -> str:
    """Detect E1 file type from filename pattern."""
    if "_nav.csv" in filename:
        return "nav"
    if "_imu.csv" in filename:
        return "imu"
    if "_wind.csv" in filename:
        return "wind"
    if ".rtcm3" in filename:
        return "rtcm3"
    if filename.endswith(".json"):
        return "processed"
    return "unknown"


def format_bytes(size: int) -> str:
    """Format byte size as human-readable string."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
