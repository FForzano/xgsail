"""NOAA NDBC adapter (realtime2 text feed, ~45 days of history).

Self-contained: the line parser used to live in ``backend.noaa_buoys`` (the
pre-redesign Boston-hardcoded buoy module, now removed) — stations are DB rows
(``wind_stations``) and can be anywhere. NDBC timestamps are UTC.
"""

from datetime import datetime, timezone
from typing import Optional

import requests

NDBC_REALTIME_URL = "https://www.ndbc.noaa.gov/data/realtime2/{station_id}.txt"

FETCH_TIMEOUT_S = 15

MPS_TO_KTS = 1.94384


def parse_ndbc_line(header: "list[str]", line: str) -> Optional[dict]:
    """Parse one NDBC data line into the wind fields we cache. Returns None
    for short/malformed lines; ``MM`` marks a missing value."""
    parts = line.split()
    if len(parts) < 5:
        return None
    try:
        observed_at = datetime(int(parts[0]), int(parts[1]), int(parts[2]),
                               int(parts[3]), int(parts[4]), tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None

    def col(name: str) -> Optional[float]:
        try:
            i = header.index(name)
        except ValueError:
            return None
        if i >= len(parts) or parts[i] == "MM":
            return None
        try:
            return float(parts[i])
        except ValueError:
            return None

    wspd, gst = col("WSPD"), col("GST")
    return {
        "observed_at": observed_at,
        "twd_deg": col("WDIR"),
        "tws_kts": round(wspd * MPS_TO_KTS, 1) if wspd is not None else None,
        "gust_kts": round(gst * MPS_TO_KTS, 1) if gst is not None else None,
    }


def fetch_station(station) -> "list[dict]":
    resp = requests.get(NDBC_REALTIME_URL.format(station_id=station.external_station_id),
                        timeout=FETCH_TIMEOUT_S)
    resp.raise_for_status()

    lines = resp.text.strip().split("\n")
    if len(lines) < 2:
        return []
    header = lines[0].lstrip("#").split()

    rows = []
    for line in lines[2:]:  # line 1 = units row
        parsed = parse_ndbc_line(header, line)
        if parsed is not None:
            rows.append(parsed)
    return rows
