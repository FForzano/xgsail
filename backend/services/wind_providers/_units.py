"""Shared unit-conversion helpers for the Cumulus-family adapters
(``cumulus_realtime.py``, ``cumulus_gauges_json.py``) — both report wind
speed in a per-station-configurable unit given alongside the reading."""

SPEED_TO_KTS = {
    "mph": 0.868976,
    "km/h": 0.539957,
    "m/s": 1.94384,
    "kts": 1.0,
    "knots": 1.0,
}


def speed_factor_to_kts(unit: str):
    """Conversion factor for ``unit`` (case-insensitive), or ``None`` if
    the unit isn't recognized."""
    return SPEED_TO_KTS.get(unit.lower())
