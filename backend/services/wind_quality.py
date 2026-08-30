"""Sensor-fault detection for a real weather station's observations.

A station whose vane or anemometer has died keeps serving well-formed
numbers, so nothing upstream errors: the feed simply repeats one value
forever. That is worse than an outage here, because a real station near
the sailing area outweighs every model in the fusion
(``xgsail_windfusion.source_weight``: ``real_station`` prior 0.9 at zero
distance vs. 0.6 for a regional model), so a frozen direction would
silently define the fused wind — and with it TWA, points of sail, VMG and
the polar — for every session at that spot.

Pure functions over observation rows: anything with ``observed_at``
(tz-aware), ``twd_deg``, ``tws_kts`` and ``gust_kts`` attributes. No ORM,
no repository, no DB.

Thresholds. Every check needs both a minimum row count and a minimum time
span: two readings a minute apart repeating themselves prove nothing, and
a burst of samples inside a few seconds is exactly what a healthy station
in a steady breeze produces. The values below are sized against the
providers we actually poll (``wind_lookup.REAL_SENSOR_PROVIDERS``):
Cumulus stations report every ~5 minutes and NOAA/METAR hourly, so six
readings spanning ten minutes is a high-cadence station repeating itself
many times over, not one hourly observation seen twice.

The flip side of those thresholds: the check only ever sees the rows of
the window it is asked about, so a short session (or a sparse feed) can
fall below them and a broken station goes unnoticed for that window. That
is deliberate — a wrong verdict on thin evidence would silently discard a
healthy station, which is the worse failure — and it is why the reason is
logged rather than persisted: the next, longer window catches it.
"""

from typing import Optional, Sequence

# A directional/speed fault needs this much evidence before we act on it.
MIN_ROWS = 6
MIN_SPAN_MINUTES = 10.0

# How much the *working* sensor must move before the frozen one counts as
# broken rather than as genuinely steady weather.
MIN_SPEED_SPREAD_FRACTION = 0.20   # peak-to-peak, as a fraction of mean speed
MIN_DIRECTION_SPREAD_DEG = 20.0    # peak-to-peak on the circle

# The frozen-feed check is far more prone to false positives than the other
# two, because a genuinely steady wind reported at coarse resolution is
# indistinguishable from it: METAR/NDBC publish hourly with direction
# rounded to 10° and speed to whole knots, so three consecutive identical
# hourly rows are normal weather. These thresholds self-limit the check to
# high-cadence stations — a 5-minute Cumulus feed crosses them within an
# hour, while an hourly provider would have to repeat itself for 12 hours.
FROZEN_FEED_MIN_ROWS = 12
FROZEN_FEED_MIN_SPAN_MINUTES = 60.0


def _span_minutes(rows: Sequence) -> float:
    times = [r.observed_at for r in rows]
    return (max(times) - min(times)).total_seconds() / 60.0


def _circular_spread_deg(angles: Sequence[float]) -> float:
    """Peak-to-peak spread of directions on the circle: the complement of the
    widest empty gap between consecutive angles. 350° and 10° span 20°, not
    340°."""
    ordered = sorted(a % 360.0 for a in angles)
    if len(ordered) < 2:
        return 0.0
    gaps = [b - a for a, b in zip(ordered, ordered[1:])]
    gaps.append(ordered[0] + 360.0 - ordered[-1])
    return 360.0 - max(gaps)


def _speed_spread_fraction(speeds: Sequence[float]) -> float:
    mean = sum(speeds) / len(speeds)
    if mean <= 0.0:
        return 0.0
    return (max(speeds) - min(speeds)) / mean


def station_readings_are_faulty(rows: Sequence) -> Optional[str]:
    """Reason string if this station's readings must not be used, ``None`` if
    they are usable.

    A reason rather than a bool because the caller logs it and an operator
    has to know *which* sensor to go and look at.

    Three faults, all of them "one channel repeats while the other moves":

    - stuck vane — identical ``twd_deg`` while ``tws_kts`` varies;
    - stuck anemometer — identical non-zero ``tws_kts`` while ``twd_deg``
      varies (a constant *zero* speed is genuine calm, not a fault);
    - frozen feed — ``twd_deg``, ``tws_kts`` and ``gust_kts`` all identical
      with ``tws_kts > 0``, behind the stricter thresholds above.

    ``None`` values are never evidence of anything: a row missing the field
    under examination is dropped from that check before the row count and
    span are measured, so a sparse feed falls below the thresholds and is
    left alone rather than being read as "the same value again". The one
    exception is ``gust_kts`` in the frozen-feed check, where a gust that is
    absent from *every* row is treated as one uniform value — the fault is
    carried by direction and speed there, and a gust that is present in some
    rows and absent in others is a feed that is still changing, so it does
    not count as frozen.
    """
    if not rows:
        return None

    for check in (_stuck_vane, _stuck_anemometer, _frozen_feed):
        reason = check(rows)
        if reason:
            return reason
    return None


def _stuck_vane(rows: Sequence) -> Optional[str]:
    usable = [r for r in rows if r.twd_deg is not None and r.tws_kts is not None]
    if len(usable) < MIN_ROWS or _span_minutes(usable) < MIN_SPAN_MINUTES:
        return None

    directions = {r.twd_deg for r in usable}
    # Exact float equality is the right test: these numbers came out of a text
    # feed already rounded by the station, so "the same value was reported
    # again" is literally the same float. Do not soften this into a tolerance.
    if len(directions) != 1:
        return None

    speeds = [r.tws_kts for r in usable]
    if _speed_spread_fraction(speeds) < MIN_SPEED_SPREAD_FRACTION:
        return None

    return (f"stuck vane: {len(usable)} readings over {_span_minutes(usable):.0f} min "
            f"all report twd {next(iter(directions))}° while wind speed varies "
            f"{min(speeds)}–{max(speeds)} kts")


def _stuck_anemometer(rows: Sequence) -> Optional[str]:
    usable = [r for r in rows if r.twd_deg is not None and r.tws_kts is not None]
    if len(usable) < MIN_ROWS or _span_minutes(usable) < MIN_SPAN_MINUTES:
        return None

    speeds = {r.tws_kts for r in usable}  # exact equality, see _stuck_vane
    if len(speeds) != 1:
        return None
    speed = next(iter(speeds))
    if speed <= 0.0:
        return None

    directions = [r.twd_deg for r in usable]
    spread = _circular_spread_deg(directions)
    if spread < MIN_DIRECTION_SPREAD_DEG:
        return None

    return (f"stuck anemometer: {len(usable)} readings over {_span_minutes(usable):.0f} min "
            f"all report {speed} kts while direction varies over {spread:.0f}°")


def _frozen_feed(rows: Sequence) -> Optional[str]:
    usable = [r for r in rows if r.twd_deg is not None and r.tws_kts is not None]
    if (len(usable) < FROZEN_FEED_MIN_ROWS
            or _span_minutes(usable) < FROZEN_FEED_MIN_SPAN_MINUTES):
        return None

    # Exact equality, see _stuck_vane. ``gust_kts`` keeps ``None`` in the set
    # on purpose: uniformly absent is one value, sometimes-absent is change.
    if len({r.twd_deg for r in usable}) != 1:
        return None
    if len({r.tws_kts for r in usable}) != 1:
        return None
    if len({r.gust_kts for r in usable}) != 1:
        return None

    speed = usable[0].tws_kts
    if speed <= 0.0:
        return None

    return (f"frozen feed: {len(usable)} identical readings over "
            f"{_span_minutes(usable):.0f} min (twd {usable[0].twd_deg}°, {speed} kts)")


__all__ = ["station_readings_are_faulty", "MIN_ROWS", "MIN_SPAN_MINUTES",
           "MIN_SPEED_SPREAD_FRACTION", "MIN_DIRECTION_SPREAD_DEG",
           "FROZEN_FEED_MIN_ROWS", "FROZEN_FEED_MIN_SPAN_MINUTES"]
