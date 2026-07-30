"""Aggregates for the wearable physiological streams.

One function per concern, keyed off the sensor type, because the four series
mean genuinely different things:

- ``heart_rate`` — instantaneous bpm; summarise as min/avg/max plus the span it
  actually covers (a watch can start late or lose contact mid-outing).
- ``energy`` — a *cumulative* active-energy counter, not a per-sample reading
  (``docs/device-protocol.md`` §9.2). Totalled from its increments, so a watch
  that restarts mid-session and resets the counter doesn't wipe out the energy
  burned before it.
- ``hrv`` (SDNN, ms) and ``respiration`` (breaths/min) — sparse and irregular;
  a mean is all the data supports.

Returns only the keys the given series can support, so the backend can merge
callbacks (the four files arrive independently) instead of overwriting.
"""

from datetime import datetime, timezone

# Value column per sensor type, mirroring handler.SCALAR_SENSOR_COLUMNS.
_VALUE_COLUMNS = {
    'heart_rate': 'bpm',
    'energy': 'kcal',
    'hrv': 'ms',
    'respiration': 'brpm',
}


def _parse_t(raw):
    """ISO 8601 (the watch writes UTC with a trailing Z) -> aware datetime."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _values(points, column):
    """``(timestamp, value)`` pairs in time order, skipping unusable rows."""
    out = []
    for p in points or []:
        t = _parse_t(p.get('t'))
        v = p.get(column)
        if t is None or v is None:
            continue
        try:
            out.append((t, float(v)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda pair: pair[0])
    return out


def _span_seconds(pairs):
    return (pairs[-1][0] - pairs[0][0]).total_seconds() if len(pairs) > 1 else 0.0


def cumulative_total(pairs):
    """Total burned from a cumulative counter, as the sum of its rises.

    Deliberately not ``last - first``: if the watch restarts mid-session the
    counter goes back to zero, which would make that subtraction report only
    what happened after the restart (or a negative number). Summing positive
    increments treats each restart as a fresh run and keeps the earlier energy.
    """
    total = 0.0
    for (_, prev), (_, curr) in zip(pairs, pairs[1:]):
        if curr > prev:
            total += curr - prev
    # A single sample carries no increment, but it is itself a running total.
    if not total and len(pairs) == 1:
        total = max(pairs[0][1], 0.0)
    return total


def physio_stats(sensor_type: str, points: list) -> dict:
    """Aggregates for one processed physiological series. ``{}`` when the series
    has nothing usable in it — no key means "leave what's stored alone"."""
    column = _VALUE_COLUMNS.get(sensor_type)
    if column is None:
        return {}
    pairs = _values(points, column)
    if not pairs:
        return {}
    values = [v for _, v in pairs]

    if sensor_type == 'heart_rate':
        return {
            'avg_hr_bpm': round(sum(values) / len(values), 1),
            'max_hr_bpm': round(max(values), 1),
            'min_hr_bpm': round(min(values), 1),
            'hr_duration_s': int(_span_seconds(pairs)),
        }

    if sensor_type == 'energy':
        total = cumulative_total(pairs)
        out = {'total_kcal': round(total, 1)}
        minutes = _span_seconds(pairs) / 60.0
        if minutes > 0:
            out['avg_kcal_per_min'] = round(total / minutes, 2)
        return out

    if sensor_type == 'hrv':
        return {'avg_hrv_ms': round(sum(values) / len(values), 1)}

    if sensor_type == 'respiration':
        return {'avg_resp_brpm': round(sum(values) / len(values), 1)}

    return {}


def sample_rate_hz(points: list, sensor_type: str = None):
    """Observed sampling rate of a series, or None if it can't be measured.

    Physiological streams are not 1 Hz: heart rate arrives every few seconds and
    HRV/respiration far more sparsely still, at whatever cadence HealthKit
    chooses. Reporting a real rate keeps the UI from claiming a precision the
    data doesn't have.
    """
    column = _VALUE_COLUMNS.get(sensor_type) if sensor_type else None
    pairs = _values(points, column) if column else []
    span = _span_seconds(pairs)
    if span <= 0:
        return None
    # Intervals, not samples: n points span n-1 gaps.
    return round((len(pairs) - 1) / span, 3)
