"""FastAPI backend for SailFrames analysis dashboard.

Composition root only: builds the app, wires middleware + the RBAC startup
seed, includes every router from ``web/api/routers`` (one module per resource),
and mounts the static frontend last. All endpoint logic lives in the router
modules; shared HTTP helpers live in ``routers/_common.py``. Designed to run
locally or behind API Gateway in AWS.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import ALL_ROUTERS

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


@app.on_event("startup")
def _seed_rbac():
    """Seed default RBAC roles/permissions when using the Postgres backend."""
    if os.environ.get("SAILFRAMES_METADATA_BACKEND", "object").lower() == "postgres":
        from .auth import seed_defaults
        from .db import get_sessionmaker
        seed_defaults(get_sessionmaker())


# Include every resource router (E1 fleet, sessions, data, analysis, boats,
# leaderboard, video, buoys, races/regattas/racedays, fleet status, ingest).
for _router in ALL_ROUTERS:
    app.include_router(_router)


# --- Static files (frontend) ---
# Mounted LAST so the catch-all "/" does not shadow the API routes above.
# Serves the web directory (contains race.html, index.html, assets/).
web_dir = Path(__file__).parent.parent
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="frontend")
