"""Device management endpoints (``/api/devices``, ``/api/device-types``).

Claim flow per docs/device-protocol.md §2: an authenticated user mints a
claim code for a target (self / boat / club); the device confirms it with its
``external_id`` — possession of a valid code is the credential, so the confirm
endpoint takes no user auth — and receives its one-time ``device_api_key``
(stored server-side only as a hash). Rotate-key and revoke are owner actions.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_superadmin, require_user, verify_csrf
from ..auth.device import (
    claim_code_expiry,
    hash_device_key,
    new_claim_code,
    new_device_key,
    throttle_claim_confirm,
)
from ..auth import user_has_permission
from ..schemas import (
    ClaimConfirmModel,
    ClaimRequestModel,
    DeviceTypeWriteModel,
    DeviceUpdateModel,
)
from ..storage import BlobNotFound
from ._common import blob, repos

router = APIRouter(prefix="/api", tags=["devices"])


def _user_manages_device(user, device) -> bool:
    """Owner rule from the matrix: personal owner, boat owner/admin, or
    club.manage on the owning club. Superadmin always."""
    if user is None:
        return False
    if user.is_superadmin:
        return True
    if device.owner_user_id is not None:
        return device.owner_user_id == user.id
    if device.owner_boat_id is not None:
        return repos.boats.is_member(device.owner_boat_id, user.id, roles=["owner", "admin"])
    if device.owner_club_id is not None:
        return user_has_permission(user, "club.manage", club_id=device.owner_club_id)
    return False


def _require_device(device_id: uuid.UUID):
    device = repos.devices.get(device_id)
    if device is None:
        raise HTTPException(404, "Device not found")
    return device


def _validate_claim_target(user, body: ClaimRequestModel) -> None:
    targets = [body.owner_user_id, body.owner_boat_id, body.owner_club_id]
    if sum(t is not None for t in targets) != 1:
        raise HTTPException(422, "Exactly one claim target is required")
    if body.owner_user_id is not None:
        if body.owner_user_id != user.id and not user.is_superadmin:
            raise HTTPException(403, "Personal devices can only be claimed for yourself")
    elif body.owner_boat_id is not None:
        if repos.boats.get(body.owner_boat_id) is None:
            raise HTTPException(404, "Boat not found")
        if not (user.is_superadmin or repos.boats.is_member(
                body.owner_boat_id, user.id, roles=["owner", "admin"])):
            raise HTTPException(403, "Boat owner/admin required")
    else:
        if repos.clubs.get(body.owner_club_id) is None:
            raise HTTPException(404, "Club not found")
        if not (user.is_superadmin or user_has_permission(
                user, "club.manage", club_id=body.owner_club_id)):
            raise HTTPException(403, "Club manager required")


# --- device types (superadmin catalog) --------------------------------------

@router.get("/device-types")
def list_device_types():
    return [t.to_dict() for t in repos.devices.list_types()]


@router.post("/device-types")
def create_device_type(body: DeviceTypeWriteModel, request: Request):
    verify_csrf(request)
    require_superadmin(request)
    if not body.name or not body.category or not body.parser_key:
        raise HTTPException(422, "name, category and parser_key are required")
    return repos.devices.create_type(body.model_dump(exclude_unset=True)).to_dict()


@router.patch("/device-types/{type_id}")
def update_device_type(type_id: uuid.UUID, body: DeviceTypeWriteModel, request: Request):
    verify_csrf(request)
    require_superadmin(request)
    updated = repos.devices.update_type(type_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(404, "Device type not found")
    return updated.to_dict()


@router.delete("/device-types/{type_id}")
def delete_device_type(type_id: uuid.UUID, request: Request):
    verify_csrf(request)
    require_superadmin(request)
    if not repos.devices.delete_type(type_id):
        raise HTTPException(404, "Device type not found")
    return {"ok": True}


# --- claim flow ---------------------------------------------------------------

@router.post("/devices/claims")
def create_claim(body: ClaimRequestModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if repos.devices.get_type(body.device_type_id) is None:
        raise HTTPException(404, "Device type not found")
    _validate_claim_target(user, body)
    code = new_claim_code()
    device = repos.devices.create_claim(
        device_type_id=body.device_type_id,
        nickname=body.nickname,
        owner_user_id=body.owner_user_id,
        owner_boat_id=body.owner_boat_id,
        owner_club_id=body.owner_club_id,
        claim_code=code,
        expires_at=claim_code_expiry(),
    )
    return {
        "device_id": device.id,
        "claim_code": code,
        "expires_at": device.claim_code_expires_at,
    }


@router.post("/devices/claim/confirm")
def confirm_claim(body: ClaimConfirmModel, request: Request):
    """No user auth — possession of a valid claim_code is the credential
    (docs/device-protocol.md §2.3). Returns the one-time device_api_key."""
    throttle_claim_confirm(request)
    if not body.external_id.strip() or not body.claim_code.strip():
        raise HTTPException(400, "external_id and claim_code are required")
    device = repos.devices.get_by_claim_code(body.claim_code.strip())
    if device is None:
        raise HTTPException(404, "Unknown claim code")
    if device.claim_code_expires_at is not None and \
            datetime.now(timezone.utc) >= device.claim_code_expires_at:
        raise HTTPException(409, "Claim code expired")
    if repos.devices.get_claimed_by_external_id(body.external_id.strip()) is not None:
        raise HTTPException(409, "external_id already claimed")
    api_key = new_device_key()
    # claimed_by: the user who generated the code — for user/boat targets we
    # know it only via the claim row's owner; audit uses owner_user_id when
    # present, else NULL (the claim creator is not persisted on the row).
    claimed_by = device.owner_user_id
    device = repos.devices.confirm_claim(
        device.id,
        external_id=body.external_id.strip(),
        api_key_hash=hash_device_key(api_key),
        claimed_by=claimed_by,
    )
    return {
        "device_id": device.id,
        "device_api_key": api_key,  # shown once, stored only as hash
        "issued_at": device.claimed_at,
    }


# --- management -----------------------------------------------------------------

@router.get("/devices")
def list_devices(request: Request):
    user = require_user(request)
    if user.is_superadmin:
        devices = repos.devices.list()
    else:
        boat_ids = [b.id for b in repos.boats.list_boats_for_user(user.id, roles=["owner", "admin"])]
        club_ids = [
            c.id for c in repos.clubs.list()
            if user_has_permission(user, "club.manage", club_id=c.id)
        ]
        devices = repos.devices.list(owner_user_id=user.id,
                                     owner_boat_ids=boat_ids,
                                     owner_club_ids=club_ids)
    return [d.to_dict() for d in devices]


@router.get("/devices/{device_id}")
def get_device(device_id: uuid.UUID, request: Request):
    user = require_user(request)
    device = _require_device(device_id)
    if not _user_manages_device(user, device):
        raise HTTPException(403, "Not your device")
    return device.to_dict()


@router.get("/devices/{device_id}/health")
def get_device_health(device_id: uuid.UUID, request: Request):
    """Latest health snapshot pushed by the device (POST /api/devices/me/health)."""
    user = require_user(request)
    device = _require_device(device_id)
    if not _user_manages_device(user, device):
        raise HTTPException(403, "Not your device")
    try:
        return blob.get_json(f"health/{device_id}.json")
    except BlobNotFound:
        raise HTTPException(404, "No health snapshot yet")


@router.patch("/devices/{device_id}")
def update_device(device_id: uuid.UUID, body: DeviceUpdateModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    device = _require_device(device_id)
    if not _user_manages_device(user, device):
        raise HTTPException(403, "Not your device")
    return repos.devices.update(device_id, body.model_dump(exclude_unset=True)).to_dict()


@router.post("/devices/{device_id}/rotate-key")
def rotate_key(device_id: uuid.UUID, request: Request):
    """Invalidate the current key and mint a new one (shown once). Same
    claim/owner — not a re-claim (docs/device-protocol.md §5)."""
    verify_csrf(request)
    user = require_user(request)
    device = _require_device(device_id)
    if not _user_manages_device(user, device):
        raise HTTPException(403, "Not your device")
    if device.status != "claimed":
        raise HTTPException(409, "Device is not claimed")
    api_key = new_device_key()
    repos.devices.set_api_key_hash(device_id, hash_device_key(api_key))
    return {"device_id": device_id, "device_api_key": api_key}


@router.delete("/devices/{device_id}")
def revoke_device(device_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    device = _require_device(device_id)
    if not _user_manages_device(user, device):
        raise HTTPException(403, "Not your device")
    repos.devices.revoke(device_id)
    return {"ok": True}
