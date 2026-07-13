"""FastAPI backend for SailFrames — the single REST API.

Composition root only: builds the app, wires CORS + the RBAC startup seed, and
includes every router from ``backend/routers`` (one module per resource). All
endpoint logic lives in the router modules; shared HTTP helpers live in
``routers/_common.py``. The SPA is served by its own container, so this app is
API-only (no static mount).
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import ALL_ROUTERS

app = FastAPI(
    title="XGSail Analysis API",
    version="1.0.0",
    description="Sailboat racing analysis and replay dashboard",
)

# Credentialed cookie auth (sf_access/sf_csrf) is incompatible with a wildcard
# origin, so CORS is an explicit allow-list. In production the SPA is served
# same-origin (no CORS exercised); this list matters for the Vite dev server
# and any split-origin deploy. Override with SAILFRAMES_CORS_ORIGINS (CSV).
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "SAILFRAMES_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _seed():
    """Run migrations (via repo build) then seed the bootstrap superadmin, the
    device-type catalog, and the default RBAC roles/permissions."""
    from .auth import seed_defaults, seed_superadmin, seed_device_types
    from .db import get_sessionmaker
    from .repositories import get_repos

    repos = get_repos()  # building the SQL repos runs alembic upgrade head
    seed_superadmin(repos)
    seed_device_types(get_sessionmaker())
    seed_defaults(get_sessionmaker())


@app.get("/api/health")
def health():
    """Liveness probe (docker-compose healthcheck) — no DB/blob access."""
    return {"ok": True}


# Include every resource router (see routers/__init__.py for the er-project
# enable/disable list).
for _router in ALL_ROUTERS:
    app.include_router(_router)
