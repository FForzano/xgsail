"""NOAA NDBC adapter (realtime2 text feed, ~45 days of history).

Reuses the line parser from ``backend.noaa_buoys`` and maps its fields onto
the ``wind_observations`` shape. NDBC timestamps are UTC.
"""

from datetime import datetime, timezone

import requests

from ...noaa_buoys import NDBC_REALTIME_URL, parse_ndbc_line

FETCH_TIMEOUT_S = 15


def fetch_station(external_station_id: str) -> list[dict]:
    resp = requests.get(NDBC_REALTIME_URL.format(station_id=external_station_id),
                        timeout=FETCH_TIMEOUT_S)
    resp.raise_for_status()

    lines = resp.text.strip().split("\n")
    if len(lines) < 2:
        return []
    header = lines[0].lstrip("#").split()

    rows = []
    for line in lines[2:]:  # line 1 = units row
        parsed = parse_ndbc_line(header, line)
        if parsed is None:
            continue
        rows.append({
            "observed_at": datetime.fromtimestamp(parsed["unix_ts"], tz=timezone.utc),
            "twd_deg": parsed.get("wind_dir"),
            "tws_kts": parsed.get("wind_speed_kts"),
            "gust_kts": parsed.get("wind_gust_kts"),
        })
    return rows
