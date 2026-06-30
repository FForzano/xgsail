"""Self-hosted (MinIO) ingest + proxy endpoints for SailFrames.

Only relevant when running the Docker/MinIO stack. Provides:

- ``POST /hooks/minio`` — receives MinIO bucket-notification events and runs
  the existing process_upload pipeline (replaces the AWS S3 ObjectCreated ->
  Lambda trigger).
- ``GET /api/download/{key}`` — streams an object from MinIO so the browser
  never needs MinIO credentials or a reachable internal endpoint (replaces
  S3 presigned URLs, whose host would be the internal ``minio:9000``).
- ``GET /api/fleet/{health,sd-health,bootlog}/{boat}`` — proxies the small
  per-boat status files so fleet.html / battery.html read them through the
  API instead of directly from the bucket.

All of this is inert on the cloud deployment, where ``SAILFRAMES_S3_ENDPOINT``
is unset and these routes are simply unused (the frontend keeps hitting S3).
"""

import os
import urllib.parse

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from .storage import get_blob_store, BlobNotFound

router = APIRouter(tags=["ingest"])

HOOK_TOKEN = os.environ.get("SAILFRAMES_HOOK_TOKEN")

# Single storage abstraction (s3 | minio | local), selected from env.
blob = get_blob_store()


def _http_date(dt) -> str:
    """Format a datetime as an RFC 1123 HTTP date (for Last-Modified)."""
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


# --- Ingest webhook (MinIO ObjectCreated -> processing) ---

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
    return {"status": "ok", "processed": len(records), "result": result}


# --- Object download proxy (replaces S3 presigned URLs) ---

@router.get("/api/download/{key:path}")
def download_object(key: str):
    """Stream an object out of the blob store (keeps MinIO/local private)."""
    try:
        chunks, content_type, _ = blob.open_stream(key)
    except BlobNotFound:
        raise HTTPException(404, f"Object not found: {key}")

    filename = key.rsplit("/", 1)[-1]
    return StreamingResponse(
        chunks,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# --- Per-boat status proxies (fleet.html / battery.html) ---

def _proxy_raw_object(boat: str, filename: str, media_type: str) -> Response:
    """Return a small per-boat file from raw/{boat}/, forwarding Last-Modified."""
    key = f"raw/{boat}/{filename}"
    try:
        body = blob.get_bytes(key)
    except BlobNotFound:
        raise HTTPException(404, f"Not found: {key}")

    headers = {"Cache-Control": "no-store"}
    meta = blob.head(key)
    if meta and meta.get("last_modified"):
        headers["Last-Modified"] = _http_date(meta["last_modified"])
    return Response(content=body, media_type=media_type, headers=headers)


@router.get("/api/fleet/health/{boat}")
def fleet_health(boat: str):
    return _proxy_raw_object(boat, "_health.json", "application/json")


@router.get("/api/fleet/sd-health/{boat}")
def fleet_sd_health(boat: str):
    return _proxy_raw_object(boat, "_sd_health.json", "application/json")


@router.get("/api/fleet/bootlog/{boat}")
def fleet_bootlog(boat: str):
    return _proxy_raw_object(boat, "_boot.log", "text/plain")
