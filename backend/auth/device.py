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
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

DEVICE_KEY_PREFIX = "sfd_"

# Unambiguous alphabet (no 0/O/1/I) — codes get typed into config.txt by hand.
_CLAIM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CLAIM_CODE_LENGTH = 8
CLAIM_CODE_TTL_MIN = 15


def new_device_key() -> str:
    return DEVICE_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_device_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_claim_code() -> str:
    return "".join(secrets.choice(_CLAIM_ALPHABET) for _ in range(CLAIM_CODE_LENGTH))


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


# --- claim-confirm throttle (in-memory, per-IP) ----------------------------

_THROTTLE_MAX_PER_MIN = 10
_attempts: dict = {}


def throttle_claim_confirm(request: Request) -> None:
    """Cheap per-IP rate limit on the unauthenticated claim-confirm endpoint
    (429 per the protocol's error table). In-memory: resets on restart, which
    is acceptable for this surface."""
    ip = request.client.host if request.client else "?"
    now = time.monotonic()
    q = _attempts.setdefault(ip, deque())
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= _THROTTLE_MAX_PER_MIN:
        raise HTTPException(429, "Too many claim attempts, retry later")
    q.append(now)
