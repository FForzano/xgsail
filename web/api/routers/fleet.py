"""Per-boat fleet status proxies (``/api/fleet/*``).

Serves the small per-boat status files (``_health.json``, ``_sd_health.json``,
``_boot.log``) out of ``raw/{boat}/`` so ``fleet.html`` / ``battery.html`` read
them through the API instead of directly from the bucket (keeps MinIO/local
private; on cloud the frontend can still hit the bucket directly). Forwards
``Last-Modified`` and disables caching.
"""

from fastapi import APIRouter, HTTPException, Response

from ._common import blob
from ..storage import BlobNotFound

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


def _http_date(dt) -> str:
    """Format a datetime as an RFC 1123 HTTP date (for Last-Modified)."""
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


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


@router.get("/health/{boat}")
def fleet_health(boat: str):
    return _proxy_raw_object(boat, "_health.json", "application/json")


@router.get("/sd-health/{boat}")
def fleet_sd_health(boat: str):
    return _proxy_raw_object(boat, "_sd_health.json", "application/json")


@router.get("/bootlog/{boat}")
def fleet_bootlog(boat: str):
    return _proxy_raw_object(boat, "_boot.log", "text/plain")
