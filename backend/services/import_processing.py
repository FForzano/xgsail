"""Manual-import completion (docs/api-project.md §3, "API per caricare dati
manualmente").

After the user PUTs the file to the presigned URL, ``complete_import`` binds
it to a boat/activity/session:

- ``.gpx`` — parsed inline (small files, ``services/gpx.parse_gpx``): the gps
  stream is written to ``processed/uploads/{upload_id}/gps.json`` and
  registered directly (the backend owns the DB — no worker callback needed);
  the worker is then asked for a best-effort ``analysis.json``.
- ``.csv`` (E1-format export) — copied to ``raw/uploads/{upload_id}/`` so the
  standard storage-event → worker → callback pipeline takes over.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from ..repositories import get_repos
from ..storage import BlobNotFound, get_blob_store
from . import gpx as gpx_service
from . import ingestion


def _bucket() -> str:
    return os.environ.get("SAILFRAMES_BUCKET", "sailframes-fleet-data-prod")


def _parse_ts(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def complete_import(import_row, *, boat_id: uuid.UUID,
                    activity_id: Optional[uuid.UUID],
                    session_id: Optional[uuid.UUID],
                    subject_type: str,
                    subject_user_id: Optional[uuid.UUID],
                    started_at: Optional[datetime],
                    user_id: uuid.UUID) -> dict:
    """Create the session_upload for a completed import and start processing.

    Returns ``{import, session_upload_id, session_id}``; raises HTTPException
    on user errors (missing file, unsupported type).
    """
    repos = get_repos()
    blob = get_blob_store()

    raw_key = import_row.raw_ref
    if not raw_key or not blob.exists(raw_key):
        raise HTTPException(409, "File not uploaded yet")

    filename = import_row.original_filename.lower()
    is_gpx = filename.endswith(".gpx")
    is_csv = filename.endswith(".csv")
    if not (is_gpx or is_csv):
        raise HTTPException(422, "Unsupported file type (gpx or csv)")

    points: list[dict] = []
    if is_gpx:
        try:
            points = gpx_service.parse_gpx(blob.get_bytes(raw_key))
        except BlobNotFound:
            raise HTTPException(409, "File not uploaded yet")
        except Exception:
            repos.ingest.update_import(import_row.id, {"status": "failed"})
            raise HTTPException(422, "Could not parse GPX file")
        if not points:
            repos.ingest.update_import(import_row.id, {"status": "failed"})
            raise HTTPException(422, "GPX contains no timestamped points")
        started_at = _parse_ts(points[0]["t"])
        ended_at = _parse_ts(points[-1]["t"])
    else:
        if started_at is None:
            raise HTTPException(422, "started_at is required for CSV imports")
        ended_at = None

    # Target session: explicit, or find-or-create by boat+window.
    if session_id is not None:
        session = repos.sessions.get(session_id)
        if session is None or session.boat_id != boat_id:
            raise HTTPException(404, "Session not found for this boat")
        repos.sessions.extend_window(session.id, started_at, ended_at)
    else:
        session = ingestion.find_or_create_session(
            boat_id=boat_id, started_at=started_at, ended_at=ended_at,
            activity_id=activity_id, created_by=user_id,
        )

    upload = repos.ingest.create_upload({
        "session_id": session.id,
        "source_type": "manual_import",
        "import_id": import_row.id,
        "subject_type": subject_type,
        "subject_user_id": subject_user_id,
        "status": "processing",
    })
    repos.ingest.update_upload(upload.id, {"raw_ref": raw_key})

    if is_gpx:
        prefix = ingestion.processed_prefix(upload.id)
        data_ref = f"{prefix}gps.json"
        blob.put_json(data_ref, points)
        repos.ingest.upsert_streams(upload.id, [{
            "sensor_type": "gps", "data_ref": data_ref,
            "sample_rate_hz": None, "row_count": len(points),
        }])
        repos.ingest.set_upload_status(upload.id, "processed")
        repos.ingest.update_import(import_row.id, {"status": "processed"})
        repos.sessions.rollup_status(session.id)
        try:
            ingestion.dispatch_analysis(_bucket(), prefix)
        except Exception:
            pass  # analysis is best-effort; the gps stream is already registered
    else:
        # Copy into the standard device-upload layout; the storage event on the
        # copied key drives the worker → callback pipeline from here.
        target_key = ingestion.upload_raw_key(upload.id, import_row.original_filename)
        blob.put_bytes(target_key, blob.get_bytes(raw_key))
        repos.ingest.update_import(import_row.id, {"status": "processed"})

    return {
        "import": repos.ingest.get_import(import_row.id).to_dict(),
        "session_upload_id": upload.id,
        "session_id": session.id,
    }
