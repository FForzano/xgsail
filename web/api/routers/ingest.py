"""Self-hosted (MinIO) ingest webhook (``POST /hooks/minio``).

Receives MinIO bucket-notification events and runs the existing
process_upload pipeline — the self-hosted replacement for the AWS S3
ObjectCreated -> Lambda trigger. Inert on the cloud deployment, where
``SAILFRAMES_S3_ENDPOINT`` is unset and MinIO never fires this hook.

The companion self-hosted plumbing lives alongside this router:
``download.py`` (object download proxy) and ``fleet.py`` (per-boat status
proxies).
"""

import logging
import os
import urllib.parse

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["ingest"])

logger = logging.getLogger(__name__)

HOOK_TOKEN = os.environ.get("SAILFRAMES_HOOK_TOKEN")


def _attribute_sessions(records: list) -> None:
    """Phase 4/5 ingest hook: resolve the device→boat snapshot for each freshly
    processed session and persist ``boat_id``/``boat`` into the authoritative
    store (DB row on Postgres, ``manifest.json`` on object) via
    ``SessionRepo.upsert``.

    Best-effort and idempotent: it never overwrites a session already claimed
    (``owner_user_id`` set) and preserves crew/visibility. Wrapped by the caller
    so an attribution failure can never fail the ingest itself. Attribution uses
    the resolution order in ``DeviceRepo.resolve_boat`` (covering assignment
    window at ``start_time`` → ``default_boat_id`` → unclaimed)."""
    from ..repositories import get_repos

    repos = get_repos()
    seen = set()
    for record in records:
        try:
            key = record["s3"]["object"]["key"]  # raw/{device_id}/{date}/{file}.csv
        except (KeyError, TypeError):
            continue
        parts = key.split("/")
        if len(parts) < 4:
            continue
        device_id, date = parts[1], parts[2]
        if (device_id, date) in seen:
            continue
        seen.add((device_id, date))

        session = repos.sessions.get(device_id, date)
        if session is None or session.owner_user_id is not None:
            continue  # not processed yet, or already user-claimed — leave it
        at = session.start_time or date
        boat_id = repos.devices.resolve_boat(device_id, at)
        if boat_id and session.boat_id != boat_id:
            session.boat_id = boat_id
            if not session.boat:
                session.boat = boat_id
            repos.sessions.upsert(session)


@router.post("/hooks/minio")
async def minio_hook(request: Request):
    """Receive a MinIO bucket-notification and process new CSV uploads.

    MinIO posts an S3-compatible event body (``Records[].s3.bucket.name`` /
    ``object.key``), the same shape ``lambda_handler`` expects. We gate on a
    shared token, URL-decode keys, keep only raw/*.csv (so the _sd_health.json
    that processing itself writes can't loop), and run the pipeline inline.
    """
    if HOOK_TOKEN:
        auth = request.headers.get("authorization", "")
        # MinIO sends the token verbatim; tolerate an optional "Bearer " prefix.
        presented = auth[7:] if auth.lower().startswith("bearer ") else auth
        if presented != HOOK_TOKEN:
            raise HTTPException(401, "Invalid hook token")

    event = await request.json()

    records = []
    for record in event.get("Records", []):
        try:
            raw_key = record["s3"]["object"]["key"]
        except (KeyError, TypeError):
            continue
        key = urllib.parse.unquote_plus(raw_key)
        # Filter: only newly uploaded CSVs under raw/. Skips markers,
        # _health/_sd_health/_boot.log, and avoids re-triggering on the
        # _sd_health.json that process_file writes back into raw/.
        if not key.startswith("raw/") or not key.endswith(".csv"):
            continue
        # Normalize the decoded key back into the record for the pipeline.
        record = {**record, "s3": {**record["s3"],
                                   "object": {**record["s3"]["object"], "key": key}}}
        records.append(record)

    if not records:
        return {"status": "ignored", "processed": 0}

    # Import lazily: handler.py lives on PYTHONPATH only in the container.
    from handler import lambda_handler

    result = lambda_handler({"Records": records}, None)

    # Phase 4/5: attribute the freshly processed sessions to their boat. Never
    # let an attribution error fail the ingest — the manifest is already written.
    try:
        _attribute_sessions(records)
    except Exception:  # pragma: no cover - defensive
        logger.exception("session boat-attribution failed (ingest still ok)")

    return {"status": "ok", "processed": len(records), "result": result}
