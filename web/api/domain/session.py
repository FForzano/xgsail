"""Session domain model — recorded data from one device on one date.

Only the manifest-level metadata lives here; the bulk sensor payloads
(nav/imu/wind/pres) always stay in the blob store, never the DB.

⚠️ ``date`` is the **folder slug** of an outing (``YYYYMMDD`` or, when GPS time
was unavailable, ``session_NNN``) — it is the second path segment under
``raw/{device_id}/`` and the uniqueness key together with ``device_id``. It is
NOT a calendar date to compute on; treat it as an opaque identifier. See
``docs/user_plan.md`` → "Chiarimento preliminare".

Phase 5 adds the privacy/attribution fields (``owner_user_id``, ``boat_id``
snapshot, ``visibility``, ``club_id``/``group_id``/``regatta_id``/``race_id``)
plus the actual per-session ``crew`` (distinct from a boat's standing crew).
"""

from typing import Any, Optional

from .base import DomainModel


class SessionCrew(DomainModel):
    """One crew slot on a session. Exactly one of ``user_id`` / ``guest_name``
    is set — a registered user, or a guest without an account."""

    user_id: Optional[int] = None
    guest_name: Optional[str] = None
    boat_role: Optional[str] = None  # helm | trim | bow | ... (free text)


class Session(DomainModel):
    device_id: str
    date: str
    session_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_sec: Optional[int] = None
    boat: Optional[str] = None
    name: Optional[str] = None
    sensors: Any = None
    has_video: bool = False
    has_analysis: bool = False
    trim: Optional[dict] = None

    # --- Phase 5: privacy + attribution ---
    owner_user_id: Optional[int] = None
    boat_id: Optional[str] = None  # snapshot resolved at ingest (device→boat)
    visibility: str = "private"  # private | group | club | public
    club_id: Optional[int] = None
    group_id: Optional[int] = None
    regatta_id: Optional[str] = None
    race_id: Optional[str] = None
    crew: list[SessionCrew] = []
