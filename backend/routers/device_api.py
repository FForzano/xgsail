"""Device-facing upload API (``/api/devices/me/*``) — docs/device-protocol.md §4.

Every endpoint authenticates with ``Authorization: DeviceKey <key>`` (no
cookies, no CSRF). Responses follow the protocol shapes exactly — firmware is
written against them.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from ..auth import current_device
from ..schemas import (
    DeviceHealthModel,
    DeviceSessionUploadCreateModel,
    DeviceUploadPatchModel,
)
from ..services import ingestion
from ._common import blob, repos

router = APIRouter(prefix="/api/devices/me", tags=["device-api"])


@router.post("/session-uploads", status_code=201)
def create_session_upload(body: DeviceSessionUploadCreateModel, request: Request):
    device = current_device(request)
    dtype = repos.devices.get_type(device.device_type_id)

    boat_id = body.boat_id
    if boat_id is None:
        # boat_tracker defaults to its installed boat; wearables must declare.
        if dtype is not None and dtype.category == "boat_tracker":
            boat_id = device.owner_boat_id
        if boat_id is None:
            raise HTTPException(422, "boat_id is required for this device")
    if repos.boats.get(boat_id) is None:
        raise HTTPException(404, "Boat not found")
    if body.subject_type == "crew_member" and body.subject_user_id is None:
        raise HTTPException(422, "subject_user_id is required for crew_member uploads")

    session = ingestion.find_or_create_session(
        boat_id=boat_id,
        started_at=body.started_at,
        ended_at=body.ended_at,
        activity_id=body.activity_id,
        created_by=device.owner_user_id,
    )

    # Idempotent on (session, device, sequence): a retry after a lost response
    # returns the same row with a fresh presigned URL (protocol §6).
    upload = repos.ingest.get_upload_by_key(session.id, device.id, body.sequence_number)
    if upload is None:
        upload = repos.ingest.create_upload({
            "session_id": session.id,
            "source_type": "device",
            "device_id": device.id,
            "subject_type": body.subject_type,
            "subject_user_id": body.subject_user_id,
            "sequence_number": body.sequence_number,
            "is_final": body.is_final,
            "status": "pending",
        })
        repos.ingest.update_upload(upload.id, {
            "raw_ref": f"raw/uploads/{upload.id}/",
        })

    key = ingestion.upload_raw_key(upload.id, body.filename)
    url = blob.upload_ref(key, expiry=ingestion.UPLOAD_URL_EXPIRY_S)
    return {
        "session_upload_id": upload.id,
        "session_id": session.id,
        "activity_id": session.activity_id,
        "upload_url": url,
        "upload_url_expires_at": datetime.now(timezone.utc)
        + timedelta(seconds=ingestion.UPLOAD_URL_EXPIRY_S),
    }


@router.patch("/session-uploads/{upload_id}")
def patch_session_upload(upload_id: uuid.UUID, body: DeviceUploadPatchModel,
                         request: Request):
    device = current_device(request)
    upload = repos.ingest.get_upload(upload_id)
    if upload is None or upload.device_id != device.id:
        raise HTTPException(404, "Upload not found")
    changes = {}
    if body.is_final is not None:
        changes["is_final"] = body.is_final
    if body.status is not None:
        if body.status != "failed":
            raise HTTPException(422, "Devices may only report status=failed")
        changes["status"] = "failed"
    if changes:
        repos.ingest.update_upload(upload_id, changes)
        if changes.get("status") == "failed":
            repos.sessions.rollup_status(upload.session_id)
    return repos.ingest.get_upload(upload_id).to_dict()


@router.post("/health")
def post_health(body: DeviceHealthModel, request: Request):
    """Latest-wins health snapshot (battery, heap, firmware…), served back to
    owners via GET /api/devices/{id}/health."""
    device = current_device(request)
    snapshot = body.model_dump()
    snapshot["device_id"] = str(device.id)
    snapshot["external_id"] = device.external_id
    snapshot["reported_at"] = datetime.now(timezone.utc).isoformat()
    blob.put_json(f"health/{device.id}.json", snapshot)
    return {"ok": True}
