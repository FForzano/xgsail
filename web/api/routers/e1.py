"""E1 fleet raw-upload browsing endpoints (``/api/e1/*``).

Lists devices, per-device uploads grouped by date, and per-file metadata +
download reference. Read-only view over the ``raw/`` and ``processed/``
prefixes in the blob store. The actual byte streaming lives in
``download.py``.
"""

from fastapi import APIRouter, HTTPException

from ._common import (
    detect_file_type,
    format_bytes,
    generate_presigned_url,
    list_objects_with_metadata,
    blob,
)

router = APIRouter(prefix="/api/e1", tags=["e1"])


@router.get("/devices")
def list_e1_devices():
    """List all E1 devices with upload statistics."""
    objects = list_objects_with_metadata("raw/")

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
            "total_size_formatted": format_bytes(device["total_size_bytes"]),
        })

    return {"devices": sorted(result, key=lambda d: d["device_id"])}


@router.get("/devices/{device_id}/uploads")
def list_e1_uploads(
    device_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """List all uploads for a specific E1 device grouped by date."""
    raw_objects = list_objects_with_metadata(f"raw/{device_id}/")
    processed_objects = list_objects_with_metadata(f"processed/{device_id}/")

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
            "file_type": detect_file_type(filename),
            "size_bytes": obj["size"],
            "size_formatted": format_bytes(obj["size"]),
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
            "size_formatted": format_bytes(obj["size"]),
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
            "total_size_formatted": format_bytes(data["total_size_bytes"]),
            "has_manifest": any(f["filename"] == "manifest.json" for f in data["processed_files"]),
        })

    return {
        "device_id": device_id,
        "uploads": sorted(uploads, key=lambda u: u["date"], reverse=True),
    }


@router.get("/files/{device_id}/{date}/{filename:path}")
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
        "file_type": detect_file_type(filename),
        "size_bytes": meta["size"],
        "size_formatted": format_bytes(meta["size"]),
        "last_modified": last_modified,
        "content_type": meta["content_type"],
        "download_url": generate_presigned_url(key),
        "download_url_expires_in": 3600,
    }
