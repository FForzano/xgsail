"""Device domain model — tracker registry + boat-attribution windows.

A ``Device`` is a physical tracker (the E-series fleet, a self-hosted B unit, or
an ``external`` GPS). ``device_id`` is the same string the firmware puts in its
upload path (``raw/{device_id}/…`` — ``config.txt``'s ``boat_id`` key), so it is
the stable identity across ingest and the dashboard.

Two ownership shapes:

- ``owner_type=user`` — a boat-private device. ``default_boat_id`` names the
  boat it lives on; every session it records snapshots that boat.
- ``owner_type=club`` — an organisation/RC tracker. ``owned_by_club_id`` is set,
  ``default_boat_id`` is usually null, and per-outing attribution is expressed
  as ``DeviceAssignment`` windows.

``resolve_boat(at)`` (see ``DeviceRepo``) applies the order: (1) the assignment
window covering ``at`` → (2) ``default_boat_id`` → (3) unclaimed (None).
"""

from typing import Optional

from .base import DomainModel


class DeviceAssignment(DomainModel):
    id: Optional[int] = None
    device_id: str
    boat_id: str
    regatta_id: Optional[str] = None
    race_id: Optional[str] = None
    # Half-open window [valid_from, valid_to); valid_to=None = open-ended.
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[str] = None


class Device(DomainModel):
    device_id: str
    name: Optional[str] = None
    device_type: str = "sailframes_e"  # sailframes_e | sailframes_b | external
    default_boat_id: Optional[str] = None
    owner_type: str = "user"  # user | club
    registered_by: Optional[int] = None
    owned_by_club_id: Optional[int] = None
    status: str = "active"  # active | revoked
    created_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    assignments: list[DeviceAssignment] = []


# --- Attribution-window helpers (shared by both repo backends) -------------
#
# Windows are half-open [valid_from, valid_to): a null bound is open on that
# side (valid_from=None → since forever; valid_to=None → open-ended). Kept as
# pure functions so the object and SQL repos apply *identical* overlap and
# resolution logic.

def windows_overlap(
    a_from: Optional[str], a_to: Optional[str],
    b_from: Optional[str], b_to: Optional[str],
) -> bool:
    """True if half-open [a_from,a_to) and [b_from,b_to) intersect. ISO-8601
    strings compare correctly lexicographically (fixed-width, UTC). Nulls are
    open bounds: a_from/b_from None = -inf, a_to/b_to None = +inf."""
    # Intersect iff  a_from < b_to  AND  b_from < a_to, with open bounds always
    # satisfying their side.
    a_starts_before_b_ends = a_from is None or b_to is None or a_from < b_to
    b_starts_before_a_ends = b_from is None or a_to is None or b_from < a_to
    return a_starts_before_b_ends and b_starts_before_a_ends


def window_covers(valid_from: Optional[str], valid_to: Optional[str], at: str) -> bool:
    """True if ``at`` falls in the half-open window [valid_from, valid_to)."""
    if valid_from is not None and at < valid_from:
        return False
    if valid_to is not None and at >= valid_to:
        return False
    return True


def resolve_boat_from(device: Device, at: str) -> Optional[str]:
    """Boat attribution for ``device`` at instant ``at`` (ISO-8601): the
    covering assignment window wins, else ``default_boat_id``, else None."""
    for a in device.assignments:
        if window_covers(a.valid_from, a.valid_to, at):
            return a.boat_id
    return device.default_boat_id
