"""Device and system principals (docs/device-protocol.md).

- Devices authenticate every call with ``Authorization: DeviceKey <key>``;
  only the SHA-256 of the key is stored (``devices.api_key_hash``).
- ``require_system`` gates the internal endpoints called by workers and the
  wind scheduler (the permission matrix's ``system`` actor) with the shared
  ``SAILFRAMES_HOOK_TOKEN`` bearer. It hard-fails when the env is unset — no
  silently-open system surface.
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from .throttle import new_code, throttle

DEVICE_KEY_PREFIX = "sfd_"

CLAIM_CODE_LENGTH = 8
CLAIM_CODE_TTL_MIN = 15


def new_device_key() -> str:
    return DEVICE_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_device_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_claim_code() -> str:
    return new_code(CLAIM_CODE_LENGTH)


def claim_code_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=CLAIM_CODE_TTL_MIN)


def current_device(request: Request):
    """Resolve the calling device from the DeviceKey header (401 otherwise).

    Revoked/rotated keys fail the hash lookup (hash cleared or replaced), so
    a plain 401 covers every invalid-key case per the protocol."""
    from ..repositories import get_repos

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("devicekey "):
        raise HTTPException(401, "Device key required")
    key = auth[len("devicekey "):].strip()
    device = get_repos().devices.get_by_api_key_hash(hash_device_key(key))
    if device is None:
        raise HTTPException(401, "Invalid device key")
    return device


def require_system(request: Request) -> None:
    """Shared-bearer gate for internal system calls (workers, scheduler)."""
    token = os.environ.get("SAILFRAMES_HOOK_TOKEN")
    if not token:
        raise HTTPException(503, "System endpoints disabled (no hook token configured)")
    auth = request.headers.get("authorization", "")
    presented = auth[len("bearer "):] if auth.lower().startswith("bearer ") else auth
    if not presented or not hmac.compare_digest(presented, token):
        raise HTTPException(401, "Invalid system token")


# --- claim-confirm throttle ------------------------------------------------

def throttle_claim_confirm(request: Request) -> None:
    """Cheap per-IP rate limit on the unauthenticated claim-confirm endpoint
    (429 per the protocol's error table)."""
    throttle(request, bucket="claim_confirm", max_per_min=10,
             message="Too many claim attempts, retry later")
