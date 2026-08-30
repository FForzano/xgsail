"""CumulusMX ``realtimegauges.txt`` adapter — the JSON export used by the
"Steel Series Gauges" dashboard template, distinct from the older
space-separated ``realtime.txt`` (see ``cumulus_realtime.py``). Many
real-world CumulusMX installs only expose this variant.

Sample (fields we read): ``{"wspeed":"10.5","wgust":"13.8","wlatest":"8.4",
"bearing":"100","windunit":"kts","timeUTC":"2026,07,15,22,03,06",...}``.
In principle ``timeUTC`` is an explicit, unambiguous UTC timestamp
(``year,month,day,hour,minute,second``), so we prefer it over the fetch
instant. In practice some real-world installs have their station's
timezone misconfigured in CumulusMX (e.g. the offset is added instead of
subtracted), so ``timeUTC`` can be off by hours — silently pushing
observations outside the admin UI's default lookback window even though
the reading itself is fine. If it drifts too far from the fetch instant
we can't trust it, so we fall back to the fetch time instead (the file is
refetched every few seconds by the scheduler, so the fetch instant is a
good proxy for "now" regardless).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from ._units import speed_factor_to_kts, validate_direction_deg, validate_speed_kts

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_S = 15
MAX_CLOCK_DRIFT = timedelta(hours=1)


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


def parse_realtime_gauges(text: str, fetched_at: Optional[datetime] = None) -> Optional[dict]:
    """Parse one ``realtimegauges.txt`` payload into the wind fields we
    cache. Returns `None` if the payload isn't valid JSON, is missing
    `timeUTC`/`windunit`, or uses an unrecognized wind unit.

    An individual wind field that parses but is out of range (a station's
    sentinel for "no reading") becomes ``None`` without discarding the
    fields that are fine.

    ``fetched_at`` (defaults to now) is used as a sanity check and fallback
    for ``timeUTC``: if the station's clock has drifted more than
    ``MAX_CLOCK_DRIFT`` from the fetch instant, ``timeUTC`` is untrustworthy
    and we use the fetch instant instead."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None

    fetched_at = fetched_at or datetime.now(timezone.utc)
    observed_at = _parse_time_utc(data.get("timeUTC", ""))
    if observed_at is None:
        return None
    if abs(observed_at - fetched_at) > MAX_CLOCK_DRIFT:
        logger.warning(
            "cumulus_gauges_json: timeUTC %s drifted >%s from fetch instant %s, "
            "using fetch instant instead",
            observed_at, MAX_CLOCK_DRIFT, fetched_at,
        )
        observed_at = fetched_at

    factor = speed_factor_to_kts(data.get("windunit", ""))
    if factor is None:
        return None

    wspeed = _to_float(data.get("wspeed"))
    wgust = _to_float(data.get("wgust"))
    bearing = _to_float(data.get("bearing"))

    return {
        "observed_at": observed_at,
        "twd_deg": validate_direction_deg(bearing),
        "tws_kts": validate_speed_kts(round(wspeed * factor, 1) if wspeed is not None else None),
        "gust_kts": validate_speed_kts(round(wgust * factor, 1) if wgust is not None else None),
    }


def fetch_station(station) -> "list[dict]":
    fetched_at = datetime.now(timezone.utc)
    resp = requests.get(station.source_url, timeout=FETCH_TIMEOUT_S)
    resp.raise_for_status()

    parsed = parse_realtime_gauges(resp.text, fetched_at=fetched_at)
    return [parsed] if parsed is not None else []
