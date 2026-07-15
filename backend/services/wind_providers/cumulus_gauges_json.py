"""CumulusMX ``realtimegauges.txt`` adapter — the JSON export used by the
"Steel Series Gauges" dashboard template, distinct from the older
space-separated ``realtime.txt`` (see ``cumulus_realtime.py``). Many
real-world CumulusMX installs only expose this variant.

Sample (fields we read): ``{"wspeed":"10.5","wgust":"13.8","wlatest":"8.4",
"bearing":"100","windunit":"kts","timeUTC":"2026,07,15,22,03,06",...}``.
Unlike ``realtime.txt``, ``timeUTC`` is an explicit, unambiguous UTC
timestamp (``year,month,day,hour,minute,second``), so we parse
``observed_at`` from the file itself instead of using the fetch instant.
"""

import json
from datetime import datetime, timezone
from typing import Optional

import requests

from ._units import speed_factor_to_kts

FETCH_TIMEOUT_S = 15


def _parse_time_utc(value: str) -> Optional[datetime]:
    try:
        year, month, day, hour, minute, second = (int(p) for p in value.split(","))
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _to_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_realtime_gauges(text: str) -> Optional[dict]:
    """Parse one ``realtimegauges.txt`` payload into the wind fields we
    cache. Returns `None` if the payload isn't valid JSON, is missing
    `timeUTC`/`windunit`, or uses an unrecognized wind unit."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None

    observed_at = _parse_time_utc(data.get("timeUTC", ""))
    if observed_at is None:
        return None

    factor = speed_factor_to_kts(data.get("windunit", ""))
    if factor is None:
        return None

    wspeed = _to_float(data.get("wspeed"))
    wgust = _to_float(data.get("wgust"))
    bearing = _to_float(data.get("bearing"))

    return {
        "observed_at": observed_at,
        "twd_deg": bearing,
        "tws_kts": round(wspeed * factor, 1) if wspeed is not None else None,
        "gust_kts": round(wgust * factor, 1) if wgust is not None else None,
    }


def fetch_station(station) -> "list[dict]":
    resp = requests.get(station.source_url, timeout=FETCH_TIMEOUT_S)
    resp.raise_for_status()

    parsed = parse_realtime_gauges(resp.text)
    return [parsed] if parsed is not None else []
