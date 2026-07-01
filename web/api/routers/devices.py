"""Device (tracker) endpoints (``/api/devices*``).

Self-service registration of a physical tracker. Two ownership paths:

- **Boat-private** (``owner_type=user``): the caller must be ``owner``/``skipper``
  in ``boat_members`` of the target boat. ``default_boat_id`` is set; every
  session the device records snapshots that boat (no assignment windows needed).
- **Club/RC** (``owner_type=club``): the caller must manage the owning club
  (club owner, or ``raceday.manage`` scoped to the club, or superadmin).
  ``owned_by_club_id`` is set; per-outing attribution is expressed with
  ``POST /api/devices/{id}/assignments`` (bounded windows, non-overlapping).

The generated ``device_id`` is returned **once** — the operator writes it into
the device's ``config.txt`` (``boat_id`` key = the upload-path slug). It is a
random slug that never collides with the reserved fleet units ``E1``–``E6``.
"""

import re
import secrets

from fastapi import APIRouter, HTTPException, Request

from .. import domain
from ..auth import require_permission, require_user, verify_csrf
from ..schemas import DeviceAssignmentModel, DeviceRegisterModel
from ._common import now_iso, repos

router = APIRouter(prefix="/api/devices", tags=["devices"])

# Standing-crew roles on a boat that may register a boat-private device.
BOAT_MANAGE_ROLES = ["owner", "skipper"]
# Reserved identifiers of the physical fleet — a generated slug must not clash.
_RESERVED_RE = re.compile(r"^E[1-6]$", re.IGNORECASE)


def _can_manage_club(club_id: int, user, request: Request) -> bool:
    """Caller manages the club: superadmin, the club owner, or holds
    ``raceday.manage`` scoped to it (club_admin/race_officer both do)."""
    if user.is_superadmin:
        return True
    club = repos.clubs.get(club_id)
    if club is not None and club.owner_user_id == user.id:
        return True
    try:
        return require_permission(request, "raceday.manage", club_id=club_id)
    except HTTPException:
        return False


def _new_device_slug() -> str:
    """A random, non-colliding device id (e.g. ``sf-3f9a2c``)."""
    for _ in range(20):
        slug = "sf-" + secrets.token_hex(3)
        if not _RESERVED_RE.match(slug) and repos.devices.get(slug) is None:
            return slug
    raise HTTPException(500, "Could not allocate a unique device id")


@router.get("")
def list_devices():
    return {"devices": [d.to_dict() for d in repos.devices.list()]}


@router.get("/{device_id}")
def get_device(device_id: str):
    dev = repos.devices.get(device_id)
    if dev is None:
        raise HTTPException(404, f"Device not found: {device_id}")
    return dev.to_dict()


@router.post("")
def register_device(body: DeviceRegisterModel, request: Request):
    """Register a new tracker; returns the generated ``device_id`` once."""
    verify_csrf(request)
    user = require_user(request)

    if body.owner_type == "user":
        if not body.default_boat_id:
            raise HTTPException(422, "default_boat_id is required for a boat-private device")
        if repos.boats.get(body.default_boat_id) is None:
            raise HTTPException(404, f"Boat not found: {body.default_boat_id}")
        if not (user.is_superadmin
                or repos.boats.is_member(body.default_boat_id, user.id, roles=BOAT_MANAGE_ROLES)):
            raise HTTPException(403, "Must be owner/skipper of the boat")
        owned_by_club_id = None
    elif body.owner_type == "club":
        if not body.owned_by_club_id:
            raise HTTPException(422, "owned_by_club_id is required for a club device")
        if repos.clubs.get(body.owned_by_club_id) is None:
            raise HTTPException(404, f"Club not found: {body.owned_by_club_id}")
        if not _can_manage_club(body.owned_by_club_id, user, request):
            raise HTTPException(403, "Must manage the club")
        owned_by_club_id = body.owned_by_club_id
    else:
        raise HTTPException(422, "owner_type must be 'user' or 'club'")

    device = repos.devices.register(domain.Device(
        device_id=_new_device_slug(),
        name=body.name,
        device_type=body.device_type,
        default_boat_id=body.default_boat_id if body.owner_type == "user" else None,
        owner_type=body.owner_type,
        registered_by=user.id,
        owned_by_club_id=owned_by_club_id,
        status="active",
        created_at=now_iso(),
    ))
    return device.to_dict()


def _can_manage_device(device: domain.Device, user, request: Request) -> bool:
    if user.is_superadmin or device.registered_by == user.id:
        return True
    if device.owned_by_club_id is not None:
        return _can_manage_club(device.owned_by_club_id, user, request)
    if device.default_boat_id is not None:
        return repos.boats.is_member(device.default_boat_id, user.id, roles=BOAT_MANAGE_ROLES)
    return False


@router.post("/{device_id}/assignments")
def add_assignment(device_id: str, body: DeviceAssignmentModel, request: Request):
    """Attribute the device to a boat for a bounded window (409 on overlap)."""
    verify_csrf(request)
    user = require_user(request)
    device = repos.devices.get(device_id)
    if device is None:
        raise HTTPException(404, f"Device not found: {device_id}")
    if not _can_manage_device(device, user, request):
        raise HTTPException(403, "Not allowed to manage this device")
    if repos.boats.get(body.boat_id) is None:
        raise HTTPException(404, f"Boat not found: {body.boat_id}")
    try:
        assignment = repos.devices.add_assignment(domain.DeviceAssignment(
            device_id=device_id,
            boat_id=body.boat_id,
            regatta_id=body.regatta_id,
            race_id=body.race_id,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            created_by=user.id,
            created_at=now_iso(),
        ))
    except ValueError as e:
        raise HTTPException(409, str(e))
    return assignment.to_dict()


@router.get("/{device_id}/assignments")
def list_assignments(device_id: str):
    if repos.devices.get(device_id) is None:
        raise HTTPException(404, f"Device not found: {device_id}")
    return {"assignments": [a.to_dict() for a in repos.devices.list_assignments(device_id)]}
