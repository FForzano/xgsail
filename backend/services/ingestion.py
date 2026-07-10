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

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

import requests

from ..repositories import get_repos
from ..storage import get_blob_store
from . import wind_estimates, wind_lookup

logger = logging.getLogger(__name__)

SESSION_MERGE_GAP_MINUTES = 10
UPLOAD_URL_EXPIRY_S = 3600


def bucket_name() -> str:
    return os.environ.get("SAILFRAMES_BUCKET", "sailframes-fleet-data-prod")


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
        # Sessions extend their own window above — the parent activity's
        # window must widen right along with it, since replay/data endpoints
        # (GET /activities/{id}/data) filter GPS points by the *activity's*
        # started_at/ended_at, not each session's.
        repos.activities.extend_window(activity_id, started_at, ended_at)
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
    """Ask the worker to (re)build analysis.json for a processed prefix.

    Best-effort: streams are already registered by this point, and this is
    reachable directly from a user click (``POST /sessions/{id}/reanalyze``),
    so a worker/network hiccup must not bubble up as a 500 to that click."""
    url = os.environ.get("PROCESS_UPLOAD_URL")
    if not url:
        return
    record = {"analyze": {"prefix": prefix}, "bucket": bucket}
    try:
        requests.post(url, json={"Records": [record]}, timeout=_worker_timeout())
    except requests.RequestException:
        logger.warning("analysis dispatch failed for prefix %s", prefix, exc_info=True)


def activity_thumbnail_prefixes(activity_id: uuid.UUID) -> list:
    """Each sibling session's most recently processed upload prefix — the
    inputs to the worker's overlay composite (``dispatch_activity_thumbnail``).
    Shared by the automatic post-analysis trigger (``system.py``) and the
    manual "regenerate" action (``routers/activities.py``)."""
    repos = get_repos()
    prefixes = []
    for session in repos.sessions.list(activity_id=activity_id):
        uploads = repos.ingest.list_uploads(session_id=session.id)
        if not uploads:
            continue
        latest = max(uploads, key=lambda u: u.uploaded_at)
        prefixes.append(processed_prefix(latest.id))
    return prefixes


def dispatch_activity_thumbnail(bucket: str, activity_id: uuid.UUID, prefixes: list) -> None:
    """Ask the worker to (re)composite an activity's overlay thumbnail from
    every session's processed prefix (see ``upsert_session_analysis``, which
    calls this after each session's own analysis lands).

    Best-effort like ``dispatch_analysis``, but unlike that one this is also
    reachable directly from a request (the manual "regenerate" action in
    ``routers/activities.py``), so a worker/network hiccup must not bubble up
    as a 500 to that click — log it and move on, the user can retry."""
    url = os.environ.get("PROCESS_UPLOAD_URL")
    if not url:
        return
    record = {"activity_thumbnail": {"activity_id": str(activity_id), "prefixes": prefixes},
              "bucket": bucket}
    try:
        requests.post(url, json={"Records": [record]}, timeout=_worker_timeout())
    except requests.RequestException:
        logger.warning("activity thumbnail dispatch failed for %s", activity_id, exc_info=True)


WIND_WAYPOINTS_MAX = 6


def sample_wind_waypoints(points: "list[dict]", max_points: int = WIND_WAYPOINTS_MAX
                          ) -> "list[tuple[float, float]]":
    """Evenly-spaced ``(lat, lon)`` samples across a track (always including
    the first and last point), so a session that moves several km resolves
    to more than one wind station instead of just the start point — see
    ``write_wind_cache``."""
    if not points:
        return []
    if len(points) <= max_points:
        idxs = range(len(points))
    else:
        step = (len(points) - 1) / (max_points - 1)
        idxs = sorted({round(i * step) for i in range(max_points)})
    return [(points[i]["lat"], points[i]["lon"]) for i in idxs]


def _previous_wind_cache_by_cell(store, prefix: str) -> dict:
    """The prior ``wind_cache.json`` for this prefix, indexed by grid cell —
    the fallback source for ``write_wind_cache`` when a waypoint's fetch
    fails. ``{}`` if there's no previous cache (first write) or it's
    unreadable; either way there's simply nothing to fall back to."""
    try:
        old_payload = store.get_json(f"{prefix}wind_cache.json")
    except Exception:
        return {}
    if not isinstance(old_payload, list):
        return {}
    return {
        wind_estimates.grid_cell(e["lat"], e["lng"]): e
        for e in old_payload if "lat" in e and "lng" in e
    }


def write_wind_cache(prefix: str, waypoints: "list[tuple[float, float]]",
                     start: datetime, end: datetime) -> None:
    """Pre-fetch every raw wind source relevant to a session's track/time
    window, sampled at several points along the track (``waypoints`` — see
    ``sample_wind_waypoints``) rather than just the start, and drop it in
    the processed prefix as ``wind_cache.json``. No selection happens here
    — each entry bundles *every* raw source for that waypoint (real station,
    every Open-Meteo candidate model, any existing grid estimate — see
    ``wind_lookup.gather_raw_wind``); the worker's wind-estimation algorithm
    decides what to do with it (``workers/process_upload/processing/
    wind_estimation.py``).

    Waypoints landing in the same grid cell are deduped (they'd fetch
    identical raw data — see ``services/wind_estimates.grid_cell``).

    Best-effort per waypoint, merged against the previous cache on failure:
    if a waypoint's fetch raises (a provider errored — e.g. it trimmed the
    historical window we asked for), that cell falls back to whatever bundle
    it held in the *previous* ``wind_cache.json``, instead of dropping the
    cell entirely. This is deliberately scoped to actual failures, not to a
    fetch that succeeds but is legitimately empty (no station in range right
    now) — conflating the two would resurrect a station that's genuinely no
    longer there. No staleness flag is needed on the carried-over bundle:
    every observation inside it already carries its own ``observed_at``, so
    the worker's existing per-observation time decay (``source_weight``'s
    ``dt_seconds``) naturally discounts it as it ages, same as any other
    observation. The worker falls back to GPS-estimated wind only if a cell
    has neither a fresh nor a previous bundle."""
    store = get_blob_store()
    previous_by_cell = _previous_wind_cache_by_cell(store, prefix)

    payload: list[dict] = []
    seen_cells: set = set()
    for lat, lng in waypoints:
        cell = wind_estimates.grid_cell(lat, lng)
        if cell in seen_cells:
            continue  # nearby waypoints share a cell — no need to fetch it twice
        seen_cells.add(cell)
        try:
            bundle = wind_lookup.gather_raw_wind(lat, lng, start, end, gps_points=waypoints)
        except Exception:
            logger.warning("wind cache pre-fetch failed for waypoint (%s, %s) prefix %s",
                           lat, lng, prefix, exc_info=True)
            fallback = previous_by_cell.get(cell)
            if fallback is not None:
                logger.info("wind cache: keeping previous bundle for cell %s (prefix %s) "
                           "after fetch failure", cell, prefix)
                payload.append(fallback)
            continue
        payload.append({"lat": lat, "lng": lng, **bundle})
    if payload:
        try:
            # Plain json.dumps (not put_json — no UUID/datetime encoder like
            # FastAPI's) with default=str for the datetime fields inside the bundle.
            store.put_bytes(
                f"{prefix}wind_cache.json",
                json.dumps(payload, default=str).encode(),
                "application/json",
            )
        except Exception:
            logger.warning("wind cache write failed for prefix %s", prefix, exc_info=True)


def refresh_wind_cache(session_id: uuid.UUID) -> str:
    """Recompute ``wind_cache.json`` for a session's most recently uploaded
    processed prefix, sampling waypoints from its already-stored
    ``gps.json`` — for a session ingested before the current wind-gathering
    logic landed, so it can pick up improvements without a full re-import.
    Re-dispatches analysis afterwards so VMG/polar/true-wind reflect the
    refreshed cache. Raises ``ValueError`` (caller's job to turn into an
    HTTP error) if there's nothing to refresh from.

    Works for both manual GPX imports and device uploads: the worker
    normalizes every source to the same ``{lat, lon, ...}`` shape in
    ``gps.json`` (see ``workers/process_upload/analyzer.py::parse_gps``)."""
    repos = get_repos()
    session = repos.sessions.get(session_id)
    if session is None:
        raise ValueError("Session not found")
    uploads = repos.ingest.list_uploads(session_id=session_id)
    if not uploads:
        raise ValueError("No processed data for this session")
    upload = max(uploads, key=lambda u: u.uploaded_at)
    prefix = processed_prefix(upload.id)
    try:
        points = get_blob_store().get_json(f"{prefix}gps.json")
    except Exception:
        raise ValueError("No GPS track to sample wind from")
    if not points:
        raise ValueError("No GPS track to sample wind from")
    waypoints = sample_wind_waypoints(points)
    end = session.ended_at or session.started_at
    write_wind_cache(prefix, waypoints, session.started_at, end)
    dispatch_analysis(bucket_name(), prefix)
    return prefix
