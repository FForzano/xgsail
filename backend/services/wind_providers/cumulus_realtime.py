"""Cumulus ``realtime.txt`` adapter (https://www.cumuluswiki.org/a/Realtime.txt).

Self-hosted/community weather stations running Cumulus (or a compatible
derivative, e.g. CumulusMX) can be configured to regenerate a small
space-separated text file every 5-30s at a fixed URL. Fields have been
stable since Cumulus 1.9.4; we only read the low-numbered fields that have
never changed across versions (wind + units), ignoring the many
version-dependent extras (UV, solar, extrema, ...) that aren't needed here.

No maintained Python parser exists for this format (the only public
project found, ``arabiaweather/cumulusParser``, is an unpublished,
untested 5-commit JavaScript repo) — this is a from-scratch, self-contained
parser, mirroring the shape of ``ndbc.py``.
"""

from datetime import datetime, timezone
from typing import Optional

import requests

from ._units import speed_factor_to_kts

FETCH_TIMEOUT_S = 15

# Index of each field we read (0-based), per the standard realtime.txt
# layout — stable across Cumulus versions.
_IDX_WIND_AVG = 5
_IDX_WIND_LATEST = 6
_IDX_WIND_BEARING = 7
_IDX_WIND_UNIT = 13


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def parse_realtime_line(line: str) -> Optional[dict]:
    """Parse one realtime.txt line into the wind fields we cache. Returns
    `None` for short/malformed lines.

    ``observed_at`` is *not* read from the file's own date/time fields:
    their format depends on the station's locale settings (day/month order
    is ambiguous, and there's no timezone) — we use the fetch instant (UTC
    now) instead, which is accurate within the polling cadence since the
    file is effectively live.
    """
    parts = line.split()
    if len(parts) <= _IDX_WIND_UNIT:
        return None

    factor = speed_factor_to_kts(parts[_IDX_WIND_UNIT])
    if factor is None:
        return None

    avg = _to_float(parts[_IDX_WIND_AVG])
    latest = _to_float(parts[_IDX_WIND_LATEST])
    bearing = _to_float(parts[_IDX_WIND_BEARING])

    return {
        "observed_at": datetime.now(timezone.utc),
        "twd_deg": bearing,
        "tws_kts": round(avg * factor, 1) if avg is not None else None,
        "gust_kts": round(latest * factor, 1) if latest is not None else None,
    }


def fetch_station(station) -> "list[dict]":
    resp = requests.get(station.source_url, timeout=FETCH_TIMEOUT_S)
    resp.raise_for_status()

    lines = [ln for ln in resp.text.splitlines() if ln.strip()]
    if not lines:
        return []

    parsed = parse_realtime_line(lines[-1])
    return [parsed] if parsed is not None else []
