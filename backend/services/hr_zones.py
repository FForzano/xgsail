"""Heart-rate training zones derived from a user's profile.

Five zones, the conventional 50/60/70/80/90% thresholds. Two things vary with
how much the user told us about themselves, and both are reported alongside the
numbers so the UI can say which applies — a zone boundary derived from a
population formula is an estimate, not a measurement, and must not be presented
as one:

``basis``   where the maximum came from — ``measured`` (the user entered their
            own tested HRmax) or ``tanaka`` (estimated from age).
``method``  how the bands were laid out — ``hrr`` (Karvonen, on the heart-rate
            reserve between resting and max; more accurate) or ``pct_max``
            (plain percentage of maximum, when no resting rate is known).

Computed per request rather than stored with the session's aggregates: the
profile fields behind it are editable, and a user who fixes their date of birth
next month expects the zones on an old session to be right, not frozen wrong.
See ``db/models/session.py::SessionPhysioStatsORM``.

Privacy: callers may hand these bounds to anyone allowed to see the subject's
physiological data (``auth.session_physio_visible_to``), because the bounds are
derived — the inputs (``dob``, ``resting_hr_bpm``, ``max_hr_bpm``) stay private
to the user themselves.
"""

from datetime import date
from typing import Optional

# Lower bound of each zone, as a fraction of HRmax (pct_max) or of the
# heart-rate reserve (hrr). Zone 5's upper bound is the maximum itself.
_ZONE_FLOORS = (0.50, 0.60, 0.70, 0.80, 0.90)


def age_at(dob: Optional[date], on: Optional[date] = None) -> Optional[int]:
    """Whole years between ``dob`` and ``on`` (default: today). None if unknown."""
    if dob is None:
        return None
    on = on or date.today()
    years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    return years if 0 < years < 130 else None


def estimate_max_hr(age: int) -> float:
    """Tanaka et al. (2001): ``208 - 0.7 x age``.

    Preferred over the familiar ``220 - age``, which overestimates for the
    young and underestimates past middle age.
    """
    return 208.0 - 0.7 * age


def hr_zones(user, *, on: Optional[date] = None) -> Optional[dict]:
    """The five zones for ``user``, or None when their profile can't support any.

    ``on`` is the session date, so zones on an old session use the age the
    person actually was — not their age today.
    """
    measured = user.max_hr_bpm
    if measured:
        hr_max = float(measured)
        basis = "measured"
    else:
        age = age_at(user.dob, on)
        if age is None:
            return None
        hr_max = estimate_max_hr(age)
        basis = "tanaka"

    resting = user.resting_hr_bpm
    # Karvonen needs a reserve wide enough to be meaningful; a resting rate at
    # or above the maximum is a data-entry error, not a very fit sailor.
    if resting and hr_max - resting >= 40:
        floor, span, method = float(resting), hr_max - float(resting), "hrr"
    else:
        floor, span, method = 0.0, hr_max, "pct_max"

    zones = []
    for i, low in enumerate(_ZONE_FLOORS):
        high = _ZONE_FLOORS[i + 1] if i + 1 < len(_ZONE_FLOORS) else 1.0
        zones.append({
            "zone": i + 1,
            "min_bpm": round(floor + span * low),
            # Contiguous, non-overlapping: each zone ends one beat below the
            # next one's floor, so a given bpm falls in exactly one zone.
            "max_bpm": round(floor + span * high) - (1 if high < 1.0 else 0),
        })

    return {
        "hr_max_bpm": round(hr_max),
        "basis": basis,
        "method": method,
        "zones": zones,
    }
