"""Ingestion core shared by the device API, manual imports, and system
callbacks: find-or-create of activity/session for a boat+timeframe, raw-key
layout, and worker dispatch.

Key layout (docs/device-protocol.md + api-project.md):
- ``raw/uploads/{session_upload_id}/{filename}`` — device bundles and copied
  CSV imports; each object PUT fires the storage webhook.
- ``raw/imports/{import_id}/{original_filename}`` — manual import staging
  (ignored by the webhook; processing is dispatched by /complete).
- ``processed/uploads/{session_upload_id}/{sensor}.json`` — worker output,
  referenced by ``session_streams.data_ref``.
"""

import os
import uuid
from datetime import datetime
from typing import Optional

import requests

from ..repositories import get_repos

SESSION_MERGE_GAP_MINUTES = 10
UPLOAD_URL_EXPIRY_S = 3600


def upload_raw_key(session_upload_id: uuid.UUID, filename: str) -> str:
    return f"raw/uploads/{session_upload_id}/{filename}"


def import_raw_key(import_id: uuid.UUID, original_filename: str) -> str:
    return f"raw/imports/{import_id}/{original_filename}"


def processed_prefix(session_upload_id: uuid.UUID) -> str:
    return f"processed/uploads/{session_upload_id}/"


def find_or_create_session(*, boat_id: uuid.UUID, started_at: datetime,
                           ended_at: Optional[datetime] = None,
                           activity_id: Optional[uuid.UUID] = None,
                           created_by: Optional[uuid.UUID] = None):
    """The one session per boat per activity/timeframe.

    Explicit ``activity_id``: reuse that activity's session for the boat (or
    create it). Otherwise match an existing session of the boat within the
    merge gap and extend its window, else create a private solo activity +
    session (docs/er-project.md, ``activities`` note).
    """
    repos = get_repos()
    if activity_id is not None:
        for sess in repos.sessions.list(activity_id=activity_id, boat_id=boat_id):
            repos.sessions.extend_window(sess.id, started_at, ended_at)
            return repos.sessions.get(sess.id)
        return repos.sessions.create({
            "activity_id": activity_id, "boat_id": boat_id,
            "started_at": started_at, "ended_at": ended_at, "status": "pending",
        })

    sess = repos.sessions.find_for_boat_window(
        boat_id, started_at, ended_at, gap_minutes=SESSION_MERGE_GAP_MINUTES
    )
    if sess is not None:
        repos.sessions.extend_window(sess.id, started_at, ended_at)
        return repos.sessions.get(sess.id)

    activity = repos.activities.create({
        "type": "solo", "visibility": "private", "created_by": created_by,
        "started_at": started_at, "ended_at": ended_at,
    })
    return repos.sessions.create({
        "activity_id": activity.id, "boat_id": boat_id,
        "started_at": started_at, "ended_at": ended_at, "status": "pending",
    })


# --- worker dispatch ---------------------------------------------------------

def _worker_timeout() -> int:
    return int(os.environ.get("WORKER_TIMEOUT_SEC", "300"))


def dispatch_csv_key(bucket: str, key: str) -> None:
    """Send one S3-shaped record to the process_upload worker (Lambda RIE)."""
    url = os.environ.get("PROCESS_UPLOAD_URL")
    if not url:
        raise RuntimeError("PROCESS_UPLOAD_URL is not configured")
    record = {"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}
    requests.post(url, json={"Records": [record]}, timeout=_worker_timeout())


def dispatch_analysis(bucket: str, prefix: str) -> None:
    """Ask the worker to (re)build analysis.json for a processed prefix."""
    url = os.environ.get("PROCESS_UPLOAD_URL")
    if not url:
        return  # analysis is best-effort; streams already registered
    record = {"analyze": {"prefix": prefix}, "bucket": bucket}
    requests.post(url, json={"Records": [record]}, timeout=_worker_timeout())
