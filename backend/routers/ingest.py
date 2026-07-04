"""Storage-event webhook (``/hooks/minio``) — dispatch-only.

MinIO (or an S3 notification in the AWS deploy) POSTs ObjectCreated events
here; the webhook routes them to the processing workers over HTTP (Lambda
RIE endpoints). All DB writes happen later, when the worker calls back on
``/api/system/ingest/complete`` — this endpoint never touches Postgres.

Handled keys (docs/device-protocol.md layout):
- ``raw/uploads/{session_upload_id}/*.csv`` → process_upload worker
- ``raw/uploads/{session_upload_id}/*.mp4`` → video worker (when configured)
- ``raw/imports/*`` → ignored (processing is dispatched by /api/imports/{id}/complete)
- anything else → ignored
"""

import logging
import os
import urllib.parse

import requests
from fastapi import APIRouter, BackgroundTasks, Request

from ..auth import require_system

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])

UPLOADS_PREFIX = "raw/uploads/"


def _invoke_worker(url: str, records: list[dict]) -> None:
    """Runs as a background task (threadpool): the Lambda RIE invoke is
    synchronous and the worker calls BACK into this backend on completion —
    invoking inline on the event loop would deadlock the callback."""
    timeout = int(os.environ.get("WORKER_TIMEOUT_SEC", "300"))
    try:
        resp = requests.post(url, json={"Records": records}, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        logger.exception("Worker invocation failed (%s, %d records)", url, len(records))


@router.post("/hooks/minio")
async def minio_hook(request: Request, background_tasks: BackgroundTasks):
    require_system(request)
    event = await request.json()

    csv_records: list[dict] = []
    video_records: list[dict] = []
    ignored = 0
    for record in event.get("Records", []):
        s3 = record.get("s3") or {}
        key = urllib.parse.unquote_plus((s3.get("object") or {}).get("key", ""))
        if not key.startswith(UPLOADS_PREFIX):
            ignored += 1
            continue
        clean = {"s3": {"bucket": s3.get("bucket"), "object": {"key": key}}}
        if key.endswith(".csv"):
            csv_records.append(clean)
        elif key.endswith(".mp4"):
            video_records.append(clean)
        else:
            ignored += 1

    queued = {"csv": 0, "video": 0, "ignored": ignored}
    process_url = os.environ.get("PROCESS_UPLOAD_URL")
    if csv_records and process_url:
        background_tasks.add_task(_invoke_worker, process_url, csv_records)
        queued["csv"] = len(csv_records)
    video_url = os.environ.get("VIDEO_WORKER_URL")
    if video_records and video_url:
        background_tasks.add_task(_invoke_worker, video_url, video_records)
        queued["video"] = len(video_records)
    return queued
