"""Shared unit-conversion and sanity-check helpers for the wind provider
adapters (``ndbc.py``, ``cumulus_realtime.py``, ``cumulus_gauges_json.py``).

The conversion table below is used by the two Cumulus-family adapters,
which report wind speed in a per-station-configurable unit given alongside
the reading. The validators are used by all three: every adapter reads a
third-party text/JSON feed we don't control, and a station is free to emit
a sentinel (``-9999``, ``999``, ``9999.0``, a stuck ``--`` placeholder
coerced upstream to some out-of-range number, ...) for a field it can't
currently measure. ``float(...)`` parses those without complaint, so
without an explicit range check a sentinel looks like a plausible reading
and flows straight into ``wind_observations`` — and from there into wind
fusion, where a real station carries the highest reliability weight of any
source."""

SPEED_TO_KTS = {
    "mph": 0.868976,
    "km/h": 0.539957,
    "m/s": 1.94384,
    "kts": 1.0,
    "knots": 1.0,
}

# The highest surface wind gust ever reliably recorded is ~220 kt (Barrow
# Island, Australia, during Cyclone Olivia in 1996). Nothing a coastal or
# amateur weather station could genuinely observe comes close to this, but
# it sits well below the sentinel values (999, 9999, ...) stations use for
# "no reading" — so it separates real data from a mis-parsed placeholder
# without ever clipping an actual, if extreme, observation.
MAX_WIND_SPEED_KTS = 300.0


def speed_factor_to_kts(unit: str):
    """Conversion factor for ``unit`` (case-insensitive), or ``None`` if
    the unit isn't recognized."""
    return SPEED_TO_KTS.get(unit.lower())


def validate_direction_deg(deg):
    """Reject a wind direction outside ``[0, 360]`` degrees (a sentinel
    like ``-9999`` or ``999`` parses as a float without error, so this is
    the only thing standing between it and the database). ``360`` is
    normalised to ``0`` since some stations report north that way."""
    if deg is None or deg < 0 or deg > 360:
        return None
    return 0.0 if deg == 360 else deg


def validate_speed_kts(kts):
    """Reject a wind speed/gust, already converted to knots, that is
    negative or above ``MAX_WIND_SPEED_KTS``. Must run after unit
    conversion so the same bound applies regardless of the station's
    configured unit."""
    if kts is None or kts < 0 or kts > MAX_WIND_SPEED_KTS:
        return None
    return kts
