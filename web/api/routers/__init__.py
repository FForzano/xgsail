"""HTTP controller layer for SailFrames.

One module per resource, each exposing an ``APIRouter`` as ``router``. ``main``
imports ``ALL_ROUTERS`` and includes them on the app; shared HTTP helpers live
in ``_common``. This mirrors the per-aggregate split already used by
``domain/``, ``repositories/``, ``schemas/`` and ``services/``.
"""

from . import (
    e1,
    download,
    sessions,
    data,
    analysis,
    boats,
    leaderboard,
    video,
    buoys,
    regattas,
    racedays,
    races,
    fleet,
    ingest,
    auth,
    clubs,
    groups,
    devices,
)

# Order is not significant for routing here (no overlapping path patterns
# across modules); kept grouped by concern for readability.
ALL_ROUTERS = [
    # Fleet raw data + downloads
    e1.router,
    download.router,
    # Session-centric data
    sessions.router,
    data.router,
    analysis.router,
    video.router,
    leaderboard.router,
    boats.router,
    buoys.router,
    # Race structure
    regattas.router,
    racedays.router,
    races.router,
    # Self-hosted plumbing (inert on cloud)
    fleet.router,
    ingest.router,
    # User system (auth + clubs + groups + devices)
    auth.router,
    clubs.router,
    groups.router,
    devices.router,
]

__all__ = ["ALL_ROUTERS"]
