"""HTTP controller layer for SailFrames.

One module per resource, each exposing an ``APIRouter`` as ``router``. ``main``
imports ``ALL_ROUTERS`` and includes them on the app; shared HTTP helpers live
in ``_common``.

Principals per router (docs/api-project.md): cookie users (most), DeviceKey
hardware (``device_api``), hook-token system callers (``system`` + the
``ingest`` webhook), plus the token-signed upload proxy (``uploads``) and the
blob download proxy (``download``).
"""

from . import (
    auth,
    users,
    rbac,
    boats,
    clubs,
    groups,
    devices,
    device_api,
    activities,
    sessions,
    imports,
    regattas,
    racedays,
    races,
    polars,
    wind,
    system,
    ingest,
    uploads,
    download,
    video,
)

ALL_ROUTERS = [
    # Accounts & authorization
    auth.router,
    users.router,
    rbac.router,
    # Resources
    boats.router,
    clubs.router,
    groups.router,
    devices.router,
    activities.router,
    sessions.router,
    polars.router,
    # Race structure
    regattas.router,
    racedays.router,
    races.router,
    # Ingestion (device API, manual imports, storage plumbing)
    device_api.router,
    imports.router,
    ingest.router,
    uploads.router,
    download.router,
    # Wind & external data
    wind.router,
    # System callbacks (workers, scheduler)
    system.router,
    # Media playback (HLS passthrough)
    video.router,
]

__all__ = ["ALL_ROUTERS"]
