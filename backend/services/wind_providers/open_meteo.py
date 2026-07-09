"""Open-Meteo adapter — algorithmic forecast/reanalysis, no API key, no fixed
position, own accessible history (the archive endpoint covers any past date
for any lat/lng). That's exactly why it's never persisted as a "station" —
see ``db/models/wind.py`` module docstring — it's queried fresh whenever
needed instead.

Unlike the (now-removed) single-winner design, ``fetch_station``/
``fetch_historical`` return **every** candidate model's series, not one
picked for you — see ``services/wind_model_selection.fetch_all_candidates``.
Deciding which to trust (or how to blend them) is the worker's job now (see
``workers/process_upload/processing/wind_estimation.py``).
"""

from datetime import datetime, timezone
from typing import Optional

from .. import wind_model_selection

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# Historical archive — separate from the forecast endpoint above, needed to
# backfill sessions dated further back than the forecast endpoint's
# `past_days` window covers (see `fetch_historical`).
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

MS_TO_KTS = 1.94384

HOURLY_PARAM = "wind_speed_10m,wind_direction_10m,wind_gusts_10m"

# Regional models tried, finest-first, each restricted to its own coverage
# domain — Open-Meteo returns nulls (not an error) for a point outside a
# model's domain. No "default" candidate here anymore: every one that
# covers the point comes back, the worker decides what to do with them.
MODEL_CANDIDATES = (
    "icon_d2",       # DWD ICON-D2, ~2km — Central Europe
    "icon_eu",       # DWD ICON-EU, ~7km — wider Europe
    "gfs_seamless",  # NOAA GFS+HRRR blend, ~3-13km — better resolution in the US
    "ecmwf_ifs025",  # ECMWF IFS, ~28km — solid global fallback
)


def _parse_latlng(external_station_id: str) -> "tuple[float, float]":
    try:
        lat_s, lng_s = external_station_id.split(",")
        return float(lat_s), float(lng_s)
    except ValueError:
        raise ValueError(
            f"open_meteo external_station_id must be 'lat,lng', got {external_station_id!r}"
        )


def _rows_from_hourly(hourly: dict, *, model: str) -> "list[dict]":
    times = hourly.get("time", [])
    speeds = hourly.get("wind_speed_10m", [])
    dirs = hourly.get("wind_direction_10m", [])
    gusts = hourly.get("wind_gusts_10m", [])

    rows = []
    for i, t in enumerate(times):
        speed = speeds[i] if i < len(speeds) else None
        rows.append({
            "observed_at": datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
            "twd_deg": dirs[i] if i < len(dirs) else None,
            "tws_kts": round(speed * MS_TO_KTS, 1) if speed is not None else None,
            "gust_kts": round(gusts[i] * MS_TO_KTS, 1) if i < len(gusts) and gusts[i] is not None else None,
            "model": model,
        })
    return rows


def fetch_station(external_station_id: str,
                  gps_points: "Optional[list[tuple[float, float]]]" = None) -> "dict[str, list[dict]]":
    """Forecast endpoint — returns ``{model_name: rows}`` for every candidate
    that covers this point. ``gps_points``: the session's track, when the
    caller has one (see ``services/ingestion.write_wind_cache``) — not used
    for fetching itself, kept for parity/future use."""
    lat, lng = _parse_latlng(external_station_id)
    base_params = {
        "latitude": lat, "longitude": lng, "hourly": HOURLY_PARAM,
        "wind_speed_unit": "ms", "forecast_days": 3, "past_days": 1,
    }
    candidates = wind_model_selection.fetch_all_candidates(
        FORECAST_URL, base_params, MODEL_CANDIDATES, gps_points)
    return {model: _rows_from_hourly(hourly, model=model) for model, hourly in candidates.items()}


def fetch_historical(external_station_id: str, start_date: str, end_date: str,
                     gps_points: "Optional[list[tuple[float, float]]]" = None) -> "dict[str, list[dict]]":
    """Archive endpoint (``start_date``/``end_date`` as ``YYYY-MM-DD``) —
    returns ``{model_name: rows}`` for every candidate that covers this
    point/range. Used for any date-in-the-past query, since the archive
    always has it — no local caching/reconciliation needed for this
    provider (see ``db/models/wind.py`` module docstring)."""
    lat, lng = _parse_latlng(external_station_id)
    base_params = {
        "latitude": lat, "longitude": lng, "hourly": HOURLY_PARAM,
        "wind_speed_unit": "ms", "start_date": start_date, "end_date": end_date,
    }
    candidates = wind_model_selection.fetch_all_candidates(
        ARCHIVE_URL, base_params, MODEL_CANDIDATES, gps_points)
    return {model: _rows_from_hourly(hourly, model=model) for model, hourly in candidates.items()}
