"""Human-typed codes: generation, verification, and per-IP throttling.

Shared by the two surfaces that hand a short code to a human and then accept
it back over an endpoint a stranger can hit: the device claim-confirm flow
(``auth/device.py``) and the regatta share code (``routers/regattas.py``).
In-memory buckets, so they reset on restart — acceptable for both, which only
need to make guessing expensive rather than impossible.
"""

import hmac
import secrets
import time
from collections import deque
from typing import Optional

from fastapi import HTTPException

# No 0/O/1/I: these codes get read off a screen and typed by hand.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_buckets: dict = {}


def new_code(length: int) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def code_matches(presented: Optional[str], stored: Optional[str]) -> bool:
    """Verify a code the user typed against the stored one.

    Forgiving about how it was typed (surrounding space, lower case) since it
    is read off a screen or a poster, but never about absence: a missing or
    revoked stored code (``None``/empty) matches nothing, so revoking is a
    real revocation rather than a code that anything satisfies."""
    if not presented or not stored:
        return False
    return hmac.compare_digest(presented.strip().upper(), stored.strip().upper())


def throttle(request, *, bucket: str, max_per_min: int, message: str) -> None:
    """Allow at most ``max_per_min`` calls per minute per (bucket, client IP)."""
    ip = request.client.host if request.client else "?"
    now = time.monotonic()
    q = _buckets.setdefault((bucket, ip), deque())
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= max_per_min:
        raise HTTPException(429, message)
    q.append(now)
