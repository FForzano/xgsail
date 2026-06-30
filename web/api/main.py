"""FastAPI backend for SailFrames analysis dashboard.

Serves processed analysis data and manages sessions, boats,
and leaderboard endpoints. Designed to run locally or behind
API Gateway in AWS.
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from fastapi.responses import StreamingResponse

from .auth import require_admin
from .race import router as race_router
from .ingest import router as ingest_router
from .repositories import get_repos
from .storage import get_blob_store, BlobNotFound

app = FastAPI(
    title="SailFrames Analysis API",
    version="1.0.0",
    description="Sailboat racing analysis and replay dashboard",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include race/regatta router
app.include_router(race_router)
# Include self-hosted ingest webhook + download/fleet proxies (inert on cloud)
app.include_router(ingest_router)


@app.on_event("startup")
def _seed_rbac():
    """Seed default RBAC roles/permissions when using the Postgres backend."""
    if os.environ.get("SAILFRAMES_METADATA_BACKEND", "object").lower() == "postgres":
        from .auth import seed_defaults
        from .db import get_sessionmaker
        seed_defaults(get_sessionmaker())

# Configuration
DATA_PREFIX = os.environ.get("SAILFRAMES_DATA_PREFIX", "processed")

# Single storage abstraction (s3 | minio | local), selected from env.
blob = get_blob_store()
# Structured metadata (sessions, boats, …) via the repository layer.
repos = get_repos()


def _load_json(key: str) -> dict:
    """Load JSON from the configured blob store (404 if missing)."""
    try:
        return blob.get_json(key)
    except BlobNotFound:
        raise HTTPException(404, f"Data not found: {key}")


def _list_keys(prefix: str) -> list[str]:
    """List keys under prefix."""
    return blob.list_keys(prefix)


def _list_objects_with_metadata(prefix: str) -> list[dict]:
    """List objects with size and last modified metadata."""
    return blob.list_with_metadata(prefix)


def _generate_presigned_url(key: str, expiry: int = 3600) -> str:
    """A browser-fetchable reference for a key: presigned URL (AWS) or proxy
    path (MinIO / local). Backend decides; see ``BlobStore.download_ref``."""
    return blob.download_ref(key, expiry)


def _detect_file_type(filename: str) -> str:
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


def _format_bytes(size: int) -> str:
    """Format byte size as human-readable string."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


# --- E1 Fleet Data ---

@app.get("/api/e1/devices")
def list_e1_devices():
    """List all E1 devices with upload statistics."""
    objects = _list_objects_with_metadata("raw/")

    # Group by device_id
    devices = {}
    for obj in objects:
        parts = obj["key"].split("/")
        if len(parts) < 3:
            continue
        device_id = parts[1]
        date = parts[2]

        if device_id not in devices:
            devices[device_id] = {
                "device_id": device_id,
                "dates": set(),
                "total_files": 0,
                "total_size_bytes": 0,
            }

        devices[device_id]["dates"].add(date)
        devices[device_id]["total_files"] += 1
        devices[device_id]["total_size_bytes"] += obj["size"]

    # Convert to list with computed fields
    result = []
    for device in devices.values():
        dates = sorted(device["dates"])
        result.append({
            "device_id": device["device_id"],
            "first_upload": dates[0] if dates else None,
            "last_upload": dates[-1] if dates else None,
            "total_sessions": len(dates),
            "total_files": device["total_files"],
            "total_size_bytes": device["total_size_bytes"],
            "total_size_formatted": _format_bytes(device["total_size_bytes"]),
        })

    return {"devices": sorted(result, key=lambda d: d["device_id"])}


@app.get("/api/e1/devices/{device_id}/uploads")
def list_e1_uploads(
    device_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """List all uploads for a specific E1 device grouped by date."""
    raw_objects = _list_objects_with_metadata(f"raw/{device_id}/")
    processed_objects = _list_objects_with_metadata(f"processed/{device_id}/")

    # Group raw files by date
    uploads_by_date = {}
    for obj in raw_objects:
        parts = obj["key"].split("/")
        if len(parts) < 4:
            continue
        date = parts[2]
        filename = parts[3]

        # Apply date filters
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue

        if date not in uploads_by_date:
            uploads_by_date[date] = {
                "date": date,
                "raw_files": [],
                "processed_files": [],
                "total_size_bytes": 0,
            }

        uploads_by_date[date]["raw_files"].append({
            "key": obj["key"],
            "filename": filename,
            "file_type": _detect_file_type(filename),
            "size_bytes": obj["size"],
            "size_formatted": _format_bytes(obj["size"]),
            "last_modified": obj["last_modified"],
        })
        uploads_by_date[date]["total_size_bytes"] += obj["size"]

    # Add processed files
    for obj in processed_objects:
        parts = obj["key"].split("/")
        if len(parts) < 4:
            continue
        date = parts[2]
        filename = parts[3]

        if date not in uploads_by_date:
            continue

        uploads_by_date[date]["processed_files"].append({
            "key": obj["key"],
            "filename": filename,
            "sensor_type": filename.replace(".json", ""),
            "size_bytes": obj["size"],
            "size_formatted": _format_bytes(obj["size"]),
        })

    # Compute summary stats per date
    uploads = []
    for date, data in uploads_by_date.items():
        file_types = {}
        for f in data["raw_files"]:
            ft = f["file_type"]
            file_types[ft] = file_types.get(ft, 0) + 1

        uploads.append({
            **data,
            "file_type_counts": file_types,
            "total_size_formatted": _format_bytes(data["total_size_bytes"]),
            "has_manifest": any(f["filename"] == "manifest.json" for f in data["processed_files"]),
        })

    return {
        "device_id": device_id,
        "uploads": sorted(uploads, key=lambda u: u["date"], reverse=True),
    }


@app.get("/api/e1/files/{device_id}/{date}/{filename:path}")
def get_e1_file(device_id: str, date: str, filename: str):
    """Get file metadata and presigned download URL."""
    key = f"raw/{device_id}/{date}/{filename}"

    # Try raw first, then processed
    meta = blob.head(key)
    if meta is None:
        key = f"processed/{device_id}/{date}/{filename}"
        meta = blob.head(key)
    if meta is None:
        raise HTTPException(404, f"File not found: {filename}")

    last_modified = meta["last_modified"]
    last_modified = last_modified.isoformat() if hasattr(last_modified, "isoformat") else str(last_modified)

    return {
        "key": key,
        "filename": filename,
        "file_type": _detect_file_type(filename),
        "size_bytes": meta["size"],
        "size_formatted": _format_bytes(meta["size"]),
        "last_modified": last_modified,
        "content_type": meta["content_type"],
        "download_url": _generate_presigned_url(key),
        "download_url_expires_in": 3600,
    }


@app.get("/api/e1/download/{key:path}")
def download_e1_file(key: str):
    """Stream an object out of the blob store (used as the download target for
    the ``local`` backend; harmless on other backends)."""
    try:
        chunks, content_type, _ = blob.open_stream(key)
    except BlobNotFound:
        raise HTTPException(404, f"File not found: {key}")
    filename = key.rsplit("/", 1)[-1]
    return StreamingResponse(
        chunks,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# --- Sessions ---

@app.get("/api/sessions")
def list_sessions():
    """List all available race sessions."""
    sessions = []
    for s in repos.sessions.list():
        duration_sec = s.duration_sec or 0
        sessions.append({
            "device_id": s.device_id,
            "date": s.date,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "duration_sec": duration_sec,
            "duration_minutes": round(duration_sec / 60) if duration_sec else 0,
            "sensors": s.sensors if s.sensors is not None else [],
            "has_video": s.has_video,
            "has_analysis": s.has_analysis,
            "boat": s.boat,
            "name": s.name,
            "session_id": s.session_id,
        })

    return {"sessions": sorted(sessions, key=lambda s: s["date"], reverse=True)}


@app.get("/api/sessions/{device_id}/{date}")
def get_session(device_id: str, date: str):
    """Get session metadata and manifest."""
    session = repos.sessions.get(device_id, date)
    if session is None:
        raise HTTPException(404, f"Session not found: {device_id}/{date}")
    return session.to_dict()


# --- Sensor Data ---

@app.get("/api/data/{device_id}/{date}")
def get_sensor_data(
    device_id: str,
    date: str,
    sensors: str = Query("gps,imu,wind,pressure", description="Comma-separated sensor list"),
    start: float | None = None,
    end: float | None = None,
    resolution: int = Query(1, description="Downsample factor"),
):
    """Get sensor time-series data for a session, merged by timestamp.

    Returns data in merged format expected by frontend:
    {
        data: [{t, gps: {...}, imu: {...}, pressure: {...}, wind: {...}}, ...],
        start_time: "...",
        end_time: "..."
    }
    """
    # Load each sensor's data
    sensor_data = {}
    for sensor in sensors.split(","):
        sensor = sensor.strip()
        # PPK data is stored as ppk_gps.json, not ppk.json
        if sensor == "ppk":
            key = f"{DATA_PREFIX}/{device_id}/{date}/ppk_gps.json"
        else:
            key = f"{DATA_PREFIX}/{device_id}/{date}/{sensor}.json"
        try:
            data = _load_json(key)
            records = data if isinstance(data, list) else data.get("data", [])
            sensor_data[sensor] = records
        except HTTPException:
            sensor_data[sensor] = []

    # Merge by timestamp - collect all unique timestamps
    merged = {}  # timestamp -> {t, gps: {...}, imu: {...}, ...}

    for sensor, records in sensor_data.items():
        for record in records:
            t = record.get("t")
            if not t:
                continue
            if t not in merged:
                merged[t] = {"t": t}
            # Nest sensor data under sensor key (exclude 't' from nested object)
            sensor_record = {k: v for k, v in record.items() if k != "t"}
            merged[t][sensor] = sensor_record

    # Sort by timestamp and convert to list
    data = [merged[t] for t in sorted(merged.keys())]

    # Time filtering using ISO string comparison (works for chronological order)
    # Note: start/end params are currently unused as frontend filters via timeController
    # TODO: Support ISO string time bounds if needed

    # Downsample
    if resolution > 1:
        data = data[::resolution]

    # Calculate time bounds
    start_time = data[0]["t"] if data else None
    end_time = data[-1]["t"] if data else None

    return {
        "data": data,
        "start_time": start_time,
        "end_time": end_time,
    }


# --- Analysis ---

@app.get("/api/analysis/{device_id}/{date}")
def get_analysis(device_id: str, date: str):
    """Get full analysis results for a session."""
    key = f"{DATA_PREFIX}/{device_id}/{date}/analysis.json"
    return _load_json(key)


@app.get("/api/analysis/{device_id}/{date}/maneuvers")
def get_maneuvers(device_id: str, date: str):
    """Get maneuver detection results."""
    analysis = get_analysis(device_id, date)
    return {
        "maneuvers": analysis.get("maneuvers", []),
        "summary": analysis.get("maneuver_summary", {}),
    }


@app.get("/api/analysis/{device_id}/{date}/legs")
def get_legs(device_id: str, date: str):
    """Get straight-line leg analysis."""
    analysis = get_analysis(device_id, date)
    return {
        "legs": analysis.get("legs", []),
        "comparison": analysis.get("leg_comparison", {}),
    }


@app.get("/api/analysis/{device_id}/{date}/polar")
def get_polar(device_id: str, date: str):
    """Get polar diagram data."""
    analysis = get_analysis(device_id, date)
    return {"polar": analysis.get("polar", {})}


@app.get("/api/analysis/{device_id}/{date}/stats")
def get_stats(device_id: str, date: str):
    """Get statistical analysis (violin, correlations)."""
    analysis = get_analysis(device_id, date)
    return {
        "violin": analysis.get("violin", {}),
        "correlations": analysis.get("correlations", {}),
        "session_stats": analysis.get("session_stats", {}),
        "leg_ranking": analysis.get("leg_ranking", []),
    }


# --- Boats ---

@app.get("/api/boats")
def list_boats():
    """List all boat profiles."""
    return {"boats": [b.to_dict() for b in repos.boats.list()]}


@app.get("/api/boats/{boat_id}")
def get_boat(boat_id: str):
    """Get a specific boat profile."""
    boat = repos.boats.get(boat_id)
    if boat is None:
        raise HTTPException(404, f"Boat not found: {boat_id}")
    return boat.to_dict()


# --- Leaderboard ---

@app.get("/api/leaderboard")
def get_leaderboard(
    metric: str = Query("max_speed", description="Ranking metric"),
    boat_class: str | None = None,
    limit: int = 20,
):
    """Get leaderboard rankings across sessions."""
    key = f"{DATA_PREFIX}/leaderboard.json"
    try:
        data = _load_json(key)
    except HTTPException:
        return {"entries": [], "metric": metric}

    entries = data.get("entries", [])

    if boat_class:
        entries = [e for e in entries if e.get("boat_class") == boat_class]

    # Sort by metric
    entries.sort(key=lambda e: e.get(metric, 0), reverse=True)

    return {"entries": entries[:limit], "metric": metric}


# --- Video ---

@app.get("/api/video/{device_id}/{date}")
def get_video(device_id: str, date: str):
    """Get video stream URLs for a session."""
    key = f"{DATA_PREFIX}/{device_id}/{date}/manifest.json"
    manifest = _load_json(key)

    cameras = {}
    for cam in manifest.get("cameras", []):
        cam_name = cam.get("name", "default")
        cameras[cam_name] = {
            "playlist_url": cam.get("playlist_url"),
            "start_time": cam.get("start_time"),
            "end_time": cam.get("end_time"),
            "duration_sec": cam.get("duration_sec"),
        }

    return {"cameras": cameras}


# --- Session Management ---

def _delete_s3_prefix(prefix: str) -> int:
    """Delete all objects under a prefix. Returns count of deleted objects."""
    return blob.delete_prefix(prefix)


@app.delete("/api/sessions/{device_id}/{date}")
def delete_session(device_id: str, date: str, request: Request):
    """Delete a session and all its data (processed folder)."""
    require_admin(request)
    prefix = f"{DATA_PREFIX}/{device_id}/{date}/"
    deleted_count = _delete_s3_prefix(prefix)

    if deleted_count == 0:
        raise HTTPException(404, f"Session not found: {device_id}/{date}")

    return {
        "status": "deleted",
        "device_id": device_id,
        "date": date,
        "files_deleted": deleted_count,
    }


@app.post("/api/sessions/cleanup")
def cleanup_sessions(
    request: Request,
    max_duration_minutes: int = Query(15, description="Delete sessions shorter than this"),
    require_boat: bool = Query(True, description="Delete sessions with no boat selected"),
    dry_run: bool = Query(True, description="Preview without deleting"),
):
    """Bulk delete sessions that are too short or have no boat assigned.

    By default runs in dry_run mode - set dry_run=false to actually delete.
    """
    require_admin(request)
    # Get all sessions
    keys = _list_keys(f"{DATA_PREFIX}/")
    manifests = [k for k in keys if k.endswith("manifest.json")]

    to_delete = []
    kept = []

    for key in manifests:
        try:
            manifest = _load_json(key)
            parts = key.split("/")
            device_id = parts[1] if len(parts) > 2 else "unknown"
            date = parts[2] if len(parts) > 2 else "unknown"

            duration_sec = manifest.get("duration_sec", 0)
            duration_minutes = duration_sec / 60 if duration_sec else 0
            boat = manifest.get("boat")

            should_delete = False
            reason = []

            # Check duration
            if duration_minutes < max_duration_minutes:
                should_delete = True
                reason.append(f"duration {duration_minutes:.1f}min < {max_duration_minutes}min")

            # Check boat (only if require_boat is True and session is long enough)
            if require_boat and not boat and duration_minutes >= max_duration_minutes:
                should_delete = True
                reason.append("no boat selected")

            session_info = {
                "device_id": device_id,
                "date": date,
                "duration_minutes": round(duration_minutes, 1),
                "boat": boat,
                "name": manifest.get("name"),
            }

            if should_delete:
                session_info["reason"] = ", ".join(reason)
                to_delete.append(session_info)
            else:
                kept.append(session_info)

        except Exception:
            continue

    deleted_count = 0
    if not dry_run:
        for session in to_delete:
            prefix = f"{DATA_PREFIX}/{session['device_id']}/{session['date']}/"
            deleted_count += _delete_s3_prefix(prefix)

    return {
        "dry_run": dry_run,
        "criteria": {
            "max_duration_minutes": max_duration_minutes,
            "require_boat": require_boat,
        },
        "to_delete": to_delete,
        "to_delete_count": len(to_delete),
        "kept_count": len(kept),
        "files_deleted": deleted_count if not dry_run else 0,
    }


# --- NOAA Buoy Data ---

from .noaa_buoys import (
    BOSTON_BUOYS,
    get_all_buoys_data,
    get_buoy_snapshot,
    fetch_buoy_data_for_timerange,
)


@app.get("/api/buoys")
def list_buoys():
    """List all Boston Harbor area buoys with their metadata."""
    buoys = []
    for station_id, meta in BOSTON_BUOYS.items():
        buoys.append({
            "station_id": station_id,
            "name": meta["name"],
            "lat": meta["lat"],
            "lon": meta["lon"],
            "type": meta["type"],
            "data_types": meta["data"],
            "color": meta["color"],
        })
    return {"buoys": buoys}


@app.get("/api/buoys/data")
def get_buoys_data(
    start_ts: float = Query(..., description="Start timestamp (Unix)"),
    end_ts: float = Query(..., description="End timestamp (Unix)"),
):
    """
    Get NOAA buoy data for all Boston Harbor buoys within a time range.
    Returns metadata and time-series data for each buoy.
    """
    data = get_all_buoys_data(start_ts, end_ts)

    # Format response
    result = {}
    for station_id, buoy in data.items():
        result[station_id] = {
            "station_id": station_id,
            "name": buoy["name"],
            "lat": buoy["lat"],
            "lon": buoy["lon"],
            "color": buoy["color"],
            "type": buoy["type"],
            "has_data": buoy["has_data"],
            "data_points": buoy["data_points"],
        }

    return {"buoys": result}


@app.get("/api/buoys/snapshot")
def get_buoys_snapshot(
    timestamp: float = Query(..., description="Target timestamp (Unix)"),
    start_ts: float = Query(None, description="Session start (for caching)"),
    end_ts: float = Query(None, description="Session end (for caching)"),
):
    """
    Get interpolated buoy values at a specific timestamp.
    Useful for real-time display during timeline scrubbing.
    """
    # Use provided range or default to +/- 4 hours
    if start_ts is None:
        start_ts = timestamp - 4 * 3600
    if end_ts is None:
        end_ts = timestamp + 4 * 3600

    buoys_data = get_all_buoys_data(start_ts, end_ts)
    snapshot = get_buoy_snapshot(buoys_data, timestamp)

    return {"timestamp": timestamp, "buoys": snapshot}


@app.get("/api/buoys/{station_id}/data")
def get_single_buoy_data(
    station_id: str,
    start_ts: float = Query(..., description="Start timestamp (Unix)"),
    end_ts: float = Query(..., description="End timestamp (Unix)"),
):
    """Get data for a specific buoy within a time range."""
    if station_id not in BOSTON_BUOYS:
        raise HTTPException(404, f"Unknown buoy: {station_id}")

    meta = BOSTON_BUOYS[station_id]
    data_points = fetch_buoy_data_for_timerange(station_id, start_ts, end_ts)

    return {
        "station_id": station_id,
        "name": meta["name"],
        "lat": meta["lat"],
        "lon": meta["lon"],
        "color": meta["color"],
        "data_points": data_points,
    }


# --- Static files (frontend) ---

# Serve web directory (contains race.html, index.html, assets/)
web_dir = Path(__file__).parent.parent
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="frontend")
