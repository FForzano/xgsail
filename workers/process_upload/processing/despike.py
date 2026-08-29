"""Rejection of physically impossible *speed* samples in a GPS track.

The existing corruption filters are positional: ``handler.py::process_gps``
throws away fixes whose lat/lon land far from the session's median. Nothing
looked at speed, so a single bad Doppler/velocity sample in the middle of an
otherwise clean track survived all the way through analysis — and a spike
there is not a cosmetic problem:

* ``analyzer.py::_session_summary`` reports a plain ``max(speeds)``, so one
  sample defines the session's headline top speed;
* the frontend map/speed chart read the raw ``gps.json`` blob;
* worst of all, ``generate_polar(..., use_max=True)`` feeds ``polar_points``,
  which is scoped to the **boat** — one spike becomes that TWA/TWS bucket's
  target for every future session of that boat.

The observed case: a session averaging 3.9 kn with 8.4 kn gusts, containing
one 23.4 kn sample between two ~4 kn neighbours at 1 Hz.

Design constraints, in priority order:

1. **Never invent a measurement.** A flagged sample is *dropped*, never
   clamped (a clamped value is fabricated data) and never nulled (a null
   speed reads as 0 downstream — ``track.py`` defaults it — which makes
   legs/maneuvers believe the boat stopped, worse than the spike itself).
   Dropping mirrors what the lat/lon filter already does; at 1 Hz a missing
   fix is invisible.
2. **A false positive is worse than a miss.** Eating a genuine planing burst
   destroys the feature this filter exists to protect, so every criterion
   below is deliberately loose and a sample must first be a *local
   extremum* — higher (or lower) than both neighbours — before any
   magnitude test is even considered. A real acceleration is sustained: the
   sample agrees with the one after it, so it sits between its neighbours
   and is never a candidate here. That single test is what keeps a
   4 → 6 → 9 → 12 kn ramp intact.

Two complementary magnitude criteria then apply to those candidates:

* **A physical acceleration gate** — the sample differs from *both*
  neighbours by more than ``MAX_ACCEL_KTS_PER_S * dt``. Checking both sides
  is the point; a one-sided check would reject the first sample of every
  real acceleration.
* **A Hampel filter** (rolling median + MAD) as a second opinion for spikes
  too small for the gate but still statistically impossible for their
  neighbourhood.

Thresholds are chosen several times above anything a sailing boat can do:

* ``MAX_ACCEL_KTS_PER_S = 8.0`` — a planing dinghy or a foiler gains a couple
  of knots per second at best, and a wave-assisted surge maybe 3 kn/s. The
  reference spike is ~20 kn/s, so 8 kn/s catches it with a wide margin while
  leaving a factor of ~3 of headroom above real sailing. Note the 10 Hz →
  1 Hz downsample in ``handler.py::process_gps`` keeps the *fastest* sample
  of each second, which amplifies a bad reading — one more reason to stay
  well above real accelerations rather than near them.
* ``HAMPEL_K = 5.0`` with ``HAMPEL_WINDOW = 7`` — 5 robust sigmas, well past
  the usual 3, plus ``MAD_FLOOR_KTS`` so a very steady stretch (MAD ≈ 0,
  the classic Hampel failure mode) cannot make every ripple an outlier, plus
  ``MIN_ISOLATED_JUMP_KTS`` so the Hampel path never fires on a small wobble.
* ``MAX_DROP_FRACTION = 0.03`` — if more than 3% of the track looks spiky,
  the thresholds are wrong for that data rather than the data being wrong;
  nothing is dropped and a warning is logged. Silently deleting a slice of
  somebody's session is unacceptable. ``MIN_DROP_ALLOWANCE`` keeps that cap
  from disabling the filter on a short track, where a single legitimate
  spike is already a large fraction of very few samples.

The filter is idempotent (a cleaned track has no local extrema left that
exceed the gates) and no-ops safely on short tracks, missing/None speeds and
duplicate or out-of-order timestamps.
"""

import logging

from .track import to_timestamp

logger = logging.getLogger(__name__)

MAX_ACCEL_KTS_PER_S = 8.0
HAMPEL_WINDOW = 7
HAMPEL_K = 5.0
MAD_FLOOR_KTS = 1.0
MIN_ISOLATED_JUMP_KTS = 2.0
MAX_DROP_FRACTION = 0.03
MIN_DROP_ALLOWANCE = 3

_MAD_SCALE = 1.4826  # MAD -> sigma for normally distributed noise


def record_speed(record: dict):
    """Speed in knots, tolerant of the key spellings used across sources
    (GPX, E1/S1 CSV) — same variants ``track.py`` accepts. ``None`` when the
    record carries no usable speed."""
    if not isinstance(record, dict):
        return None
    for key in ("speed_kts", "speed_kn", "speed"):
        if key in record:
            value = record[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            return float(value)
    return None


def _median(values: "list[float]") -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _hampel_flag(speeds: "list", index: int, window: int, k: float) -> bool:
    """True when the sample deviates from its neighbourhood median by more
    than ``k`` robust sigmas. Neighbours with no speed are simply not part of
    the window."""
    half = window // 2
    lo = max(0, index - half)
    hi = min(len(speeds), index + half + 1)
    neighbourhood = [s for s in speeds[lo:hi] if s is not None]
    if len(neighbourhood) < 3:
        return False
    median = _median(neighbourhood)
    mad = _median([abs(s - median) for s in neighbourhood])
    sigma = max(_MAD_SCALE * mad, MAD_FLOOR_KTS)
    return abs(speeds[index] - median) > k * sigma


def despike_speed(
    records: "list[dict]",
    *,
    max_accel_kts_per_s: float = MAX_ACCEL_KTS_PER_S,
    hampel_window: int = HAMPEL_WINDOW,
    hampel_k: float = HAMPEL_K,
    max_drop_fraction: float = MAX_DROP_FRACTION,
    min_drop_allowance: int = MIN_DROP_ALLOWANCE,
) -> "tuple[list[dict], int]":
    """Drop GPS records whose speed is physically impossible for a sailing
    boat, returning ``(filtered_records, dropped_count)``.

    Records are passed through untouched (whatever speed/timestamp key
    spelling they used is preserved), so an unfiltered track is returned as
    the very same objects. The caller writes back only when
    ``dropped_count`` is non-zero.
    """
    if not isinstance(records, list) or len(records) < 3:
        return records, 0

    speeds = [record_speed(r) for r in records]
    times = []
    for r in records:
        if isinstance(r, dict) and ("timestamp" in r or "t" in r):
            try:
                times.append(to_timestamp(r.get("timestamp", r.get("t", ""))))
            except (ValueError, TypeError, OverflowError, OSError):
                # One unparseable timestamp must cost only its own sample the
                # acceleration gate, not disable the filter for the track.
                times.append(None)
        else:
            times.append(None)

    flagged = set()
    for i in range(1, len(records) - 1):
        cur, prev, nxt = speeds[i], speeds[i - 1], speeds[i + 1]
        if cur is None or prev is None or nxt is None:
            continue

        d_prev = cur - prev
        d_next = cur - nxt
        # A local extremum is the only kind of candidate: a genuine (and
        # therefore sustained) acceleration sits between its neighbours.
        if not ((d_prev > 0 and d_next > 0) or (d_prev < 0 and d_next < 0)):
            continue
        if min(abs(d_prev), abs(d_next)) < MIN_ISOLATED_JUMP_KTS:
            continue

        accel_flag = False
        t_prev, t_cur, t_next = times[i - 1], times[i], times[i + 1]
        if None not in (t_prev, t_cur, t_next):
            dt_prev = t_cur - t_prev
            dt_next = t_next - t_cur
            if dt_prev > 0 and dt_next > 0:
                accel_flag = (abs(d_prev) > max_accel_kts_per_s * dt_prev
                              and abs(d_next) > max_accel_kts_per_s * dt_next)

        if accel_flag or _hampel_flag(speeds, i, hampel_window, hampel_k):
            flagged.add(i)

    if not flagged:
        return records, 0

    allowance = max(min_drop_allowance, max_drop_fraction * len(records))
    if len(flagged) > allowance:
        logger.warning(
            "Speed despike: %d of %d samples flagged (allowance %.1f) — "
            "thresholds do not fit this track, dropping nothing",
            len(flagged), len(records), allowance,
        )
        return records, 0

    filtered = [r for i, r in enumerate(records) if i not in flagged]
    return filtered, len(flagged)
