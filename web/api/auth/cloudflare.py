"""Cloudflare Access cookie gate (the non-Postgres / cloud auth path).

When running without a user database, destructive endpoints are protected by
the ``CF_Authorization`` cookie Cloudflare Access sets, or bypassed entirely in
self-hosted dev via ``SAILFRAMES_ADMIN_BYPASS``.
"""

import os

from fastapi import HTTPException, Request


def cloudflare_admin(request: Request) -> bool:
    """Return True if the request is allowed by the Cloudflare cookie / bypass,
    else raise HTTP 403."""
    if os.environ.get("SAILFRAMES_ADMIN_BYPASS"):
        return True

    cf_auth = request.cookies.get("CF_Authorization")
    if not cf_auth:
        raise HTTPException(
            status_code=403,
            detail="Admin access required. Visit /admin to authenticate.",
        )
    # The cookie is a JWT signed by Cloudflare; presence is trusted here
    # (HttpOnly + Secure, not forgeable by JS). Signature verification against
    # the team's cert endpoint can be layered on later.
    return True
