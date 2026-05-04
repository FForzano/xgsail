"""
SailFrames API - NOAA + Synoptic Weather Data
Fetches real-time and historical wind from NOAA NDBC buoys, NWS airport
stations (api.weather.gov), and Synoptic Mesonet (which aggregates 100+
networks including WeatherFlow Tempest and personal weather stations).
"""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Synoptic Data Mesonet config. Token is set via Lambda env var; never
# committed. Bbox tight around Boston Harbor + Quincy Bay; widen if you
# expand to other racing venues.
SYNOPTIC_TOKEN = os.environ.get("SYNOPTIC_TOKEN")
SYNOPTIC_BBOX = os.environ.get("SYNOPTIC_BBOX", "-71.10,42.27,-70.85,42.42")
# Station name fragments we explicitly *prefer* (sailing centers, marine).
# Used only to bump a station's color into the marine-source palette so
# it stands out in the picker; doesn't affect inclusion.
SYNOPTIC_MARINE_HINTS = ("courageous", "sailing", "harbor", "wharf", "deer island", "yacht")

# Boston Harbor area NOAA NDBC buoys and C-MAN stations
BOSTON_BUOYS = {
    # Primary Boston Harbor stations
    "44013": {
        "name": "Boston 16NM",
        "lat": 42.346,
        "lon": -70.651,
        "type": "offshore",
        "source": "ndbc",
        "data": ["wind", "waves", "pressure", "air_temp", "water_temp"],
        "color": "#e0245e",
    },
    "CSIM3": {
        "name": "Castle Island",
        "lat": 42.341,
        "lon": -71.012,
        "type": "shore",
        "source": "ndbc",
        "data": ["wind", "air_temp"],
        "color": "#17bf63",
    },
    # Mass Bay A01 removed — too far north (42.52° vs harbor's 42.34°)
    # to be representative of Boston Harbor wind. Re-add if you start
    # racing in northern Mass Bay. Synoptic Mesonet (once activated) will
    # pick up better intermediate stations automatically.
    # "44029": { "name": "Mass Bay A01", ... },
    # FAA / NWS airport stations — fetched via aviationweather.gov for live
    # data and Iowa State Mesonet ASOS archive for history (decades back).
    "KBOS": {
        "name": "Logan Airport",
        "lat": 42.36,
        "lon": -71.01,
        "type": "airport",
        "source": "metar",
        "data": ["wind", "pressure", "air_temp"],
        "color": "#06b6d4",
    },
}

NDBC_REALTIME_URL = "https://www.ndbc.noaa.gov/data/realtime2/{station_id}.txt"

# In-memory cache (persists across Lambda invocations in same container)
_cache = {}
CACHE_TTL_SECONDS = 600  # 10 minutes


def lambda_handler(event, context):
    """Handle buoy API requests."""
    http_method = event.get('requestContext', {}).get('http', {}).get('method') or event.get('httpMethod', 'GET')
    path = event.get('rawPath', '') or event.get('path', '')
    query_params = event.get('queryStringParameters') or {}

    logger.info(f"Request: {http_method} {path}")

    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }

    if http_method == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': '{}'}

    try:
        # GET /api/buoys - list all buoys
        if path == '/api/buoys' or path.endswith('/buoys'):
            buoys = []
            for station_id, meta in BOSTON_BUOYS.items():
                buoys.append({
                    "station_id": station_id,
                    "name": meta["name"],
                    "lat": meta["lat"],
                    "lon": meta["lon"],
                    "type": meta["type"],
                    "data_types": meta["data"],
                    "color": meta["color"],
                })
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'buoys': buoys})
            }

        # GET /api/buoys/data?start_ts=&end_ts= - get all buoy data
        if '/buoys/data' in path:
            start_ts = float(query_params.get('start_ts', 0))
            end_ts = float(query_params.get('end_ts', 0))

            if not start_ts or not end_ts:
                return {
                    'statusCode': 400,
                    'headers': headers,
                    'body': json.dumps({'error': 'start_ts and end_ts are required'})
                }

            data = get_all_buoys_data(start_ts, end_ts)
            result = {}
            for station_id, buoy in data.items():
                result[station_id] = {
                    "station_id": station_id,
                    "name": buoy["name"],
                    "lat": buoy["lat"],
                    "lon": buoy["lon"],
                    "color": buoy["color"],
                    "type": buoy["type"],
                    "has_data": buoy["has_data"],
                    "data_points": buoy["data_points"],
                    # Expose source + network so the dashboard can render
                    # an honest "source" column in the wind picker
                    # (NDBC / METAR / Syn·Tempest / Syn·CWOP / etc.).
                    "source": buoy.get("source", "ndbc"),
                    "network": buoy.get("network", ""),
                }

            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'buoys': result})
            }

        # GET /api/buoys/snapshot?timestamp= - get interpolated values
        if '/buoys/snapshot' in path:
            timestamp = float(query_params.get('timestamp', 0))
            if not timestamp:
                return {
                    'statusCode': 400,
                    'headers': headers,
                    'body': json.dumps({'error': 'timestamp is required'})
                }

            start_ts = float(query_params.get('start_ts', timestamp - 4 * 3600))
            end_ts = float(query_params.get('end_ts', timestamp + 4 * 3600))

            buoys_data = get_all_buoys_data(start_ts, end_ts)
            snapshot = get_buoy_snapshot(buoys_data, timestamp)

            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'timestamp': timestamp, 'buoys': snapshot})
            }

        return {
            'statusCode': 404,
            'headers': headers,
            'body': json.dumps({'error': 'Not found'})
        }

    except Exception as e:
        logger.error(f"Error: {e}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }


def parse_ndbc_line(header: list, line: str) -> Optional[dict]:
    """Parse a single NDBC data line into a dictionary."""
    parts = line.split()
    if len(parts) < 5:
        return None

    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        hour = int(parts[3])
        minute = int(parts[4])

        timestamp = datetime(year, month, day, hour, minute)

        data = {
            "timestamp": timestamp.isoformat() + "Z",
            "unix_ts": int(timestamp.timestamp()),
        }

        col_map = {
            "WDIR": "wind_dir",
            "WSPD": "wind_speed_mps",
            "GST": "wind_gust_mps",
            "WVHT": "wave_height_m",
            "DPD": "wave_period_sec",
            "APD": "wave_avg_period_sec",
            "MWD": "wave_dir",
            "PRES": "pressure_hpa",
            "ATMP": "air_temp_c",
            "WTMP": "water_temp_c",
            "DEWP": "dew_point_c",
            "VIS": "visibility_nm",
            "PTDY": "pressure_tendency",
            "TIDE": "tide_ft",
        }

        for i, col in enumerate(header[5:], start=5):
            if col in col_map and i < len(parts):
                val = parts[i]
                if val != "MM":
                    try:
                        data[col_map[col]] = float(val)
                    except ValueError:
                        pass

        # Convert wind speed to knots
        if "wind_speed_mps" in data:
            data["wind_speed_kts"] = round(data["wind_speed_mps"] * 1.94384, 1)
        if "wind_gust_mps" in data:
            data["wind_gust_kts"] = round(data["wind_gust_mps"] * 1.94384, 1)

        return data
    except (ValueError, IndexError):
        return None


def fetch_buoy_data(station_id: str, hours_back: int = 24) -> list:
    """Fetch buoy data from NDBC for the last N hours."""
    cache_key = f"{station_id}_{hours_back}h"

    # Check cache
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if datetime.utcnow().timestamp() - cached_time < CACHE_TTL_SECONDS:
            return cached_data

    url = NDBC_REALTIME_URL.format(station_id=station_id)

    try:
        with urlopen(url, timeout=10) as response:
            text = response.read().decode('utf-8')
    except URLError as e:
        logger.warning(f"Error fetching {station_id}: {e}")
        return []

    lines = text.strip().split("\n")
    if len(lines) < 2:
        return []

    header = lines[0].replace("#", "").split()
    cutoff = datetime.utcnow() - timedelta(hours=hours_back)
    data = []

    for line in lines[1:]:
        if line.startswith("#"):
            continue
        parsed = parse_ndbc_line(header, line)
        if parsed:
            ts = datetime.fromisoformat(parsed["timestamp"].replace("Z", ""))
            if ts >= cutoff:
                data.append(parsed)

    data.sort(key=lambda x: x["unix_ts"])

    # Cache result
    _cache[cache_key] = (datetime.utcnow().timestamp(), data)

    return data


def fetch_buoy_data_for_timerange(station_id: str, start_ts: float, end_ts: float) -> list:
    """Fetch buoy data for a specific time range, with a ±30-min filter
    buffer. Short race windows (5-15 min) only contain 1-2 NDBC samples
    without buffering, which makes the wind chart look near-empty.
    Buffering lets the dashboard interpolate cleanly across the race."""
    NDBC_BUFFER_S = 1800  # ±30 min
    eff_start = start_ts - NDBC_BUFFER_S
    eff_end = end_ts + NDBC_BUFFER_S

    buffer_hours = 2
    start_dt = datetime.utcfromtimestamp(eff_start) - timedelta(hours=buffer_hours)

    hours_back = int((datetime.utcnow() - start_dt).total_seconds() / 3600) + 1
    hours_back = min(hours_back, 45 * 24)  # Max 45 days

    all_data = fetch_buoy_data(station_id, hours_back)

    filtered = [d for d in all_data if eff_start <= d["unix_ts"] <= eff_end]

    return filtered


def fetch_nws_station_data(station_id: str, hours_back: int = 24) -> list:
    """Fetch weather data from NWS weather.gov API for airport stations."""
    cache_key = f"nws_{station_id}_{hours_back}h"

    # Check cache
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if datetime.utcnow().timestamp() - cached_time < CACHE_TTL_SECONDS:
            return cached_data

    url = f"https://api.weather.gov/stations/{station_id}/observations?limit=50"

    try:
        req = Request(url, headers={
            "User-Agent": "SailFrames/1.0 (sailing analytics; contact@sailframes.com)",
            "Accept": "application/geo+json"
        })
        with urlopen(req, timeout=5) as response:
            text = response.read().decode('utf-8')
            response_data = json.loads(text)
    except Exception as e:
        logger.warning(f"Error fetching NWS {station_id}: {e}")
        # Cache empty result briefly to avoid hammering on errors
        _cache[cache_key] = (datetime.utcnow().timestamp(), [])
        return []

    features = response_data.get("features", [])
    cutoff = datetime.utcnow() - timedelta(hours=hours_back)
    data = []

    for feature in features:
        props = feature.get("properties", {})
        ts_str = props.get("timestamp")
        if not ts_str:
            continue

        try:
            # Parse ISO timestamp
            ts = datetime.fromisoformat(ts_str.replace("+00:00", "").replace("Z", ""))
            if ts < cutoff:
                continue

            point = {
                "timestamp": ts.isoformat() + "Z",
                "unix_ts": int(ts.timestamp()),
            }

            # Wind direction (degrees)
            wind_dir = props.get("windDirection", {}).get("value")
            if wind_dir is not None:
                point["wind_dir"] = wind_dir

            # Wind speed (km/h -> knots)
            wind_speed_kmh = props.get("windSpeed", {}).get("value")
            if wind_speed_kmh is not None:
                point["wind_speed_kts"] = round(wind_speed_kmh * 0.539957, 1)

            # Wind gust (km/h -> knots)
            wind_gust_kmh = props.get("windGust", {}).get("value")
            if wind_gust_kmh is not None:
                point["wind_gust_kts"] = round(wind_gust_kmh * 0.539957, 1)

            # Temperature (C)
            temp = props.get("temperature", {}).get("value")
            if temp is not None:
                point["air_temp_c"] = temp

            # Pressure (Pa -> hPa)
            pressure_pa = props.get("barometricPressure", {}).get("value")
            if pressure_pa is not None:
                point["pressure_hpa"] = round(pressure_pa / 100, 1)

            # Dew point (C)
            dewpoint = props.get("dewpoint", {}).get("value")
            if dewpoint is not None:
                point["dew_point_c"] = dewpoint

            # Only add if we have wind data
            if "wind_dir" in point or "wind_speed_kts" in point:
                data.append(point)

        except (ValueError, TypeError) as e:
            logger.debug(f"Error parsing NWS observation: {e}")
            continue

    data.sort(key=lambda x: x["unix_ts"])

    # Cache result
    _cache[cache_key] = (datetime.utcnow().timestamp(), data)

    return data


def fetch_nws_data_for_timerange(station_id: str, start_ts: float, end_ts: float) -> list:
    """Fetch NWS station data for a specific time range."""
    buffer_hours = 2
    start_dt = datetime.utcfromtimestamp(start_ts) - timedelta(hours=buffer_hours)

    hours_back = int((datetime.utcnow() - start_dt).total_seconds() / 3600) + 1
    hours_back = min(hours_back, 7 * 24)  # NWS API has ~7 days of history

    all_data = fetch_nws_station_data(station_id, hours_back)

    filtered = [d for d in all_data if start_ts <= d["unix_ts"] <= end_ts]

    return filtered


# --------------------------------------------------------------------------
# METAR sources for airport stations (KBOS / KBED / KMQE / etc.)
#
# api.weather.gov works but only retains ~7 days. Two better sources:
#   - aviationweather.gov (FAA) for the last ~168 hours, JSON, fast,
#     captures sub-hourly SPECI reports between scheduled METARs.
#   - Iowa State University Mesonet ASOS archive for historical depth
#     (decades back), CSV via CGI, no auth, no rate limit.
#
# fetch_metar_data_for_timerange() is a tiered router: try the freshest
# source first, fall back to deeper history, and finally to api.weather.gov
# as a last resort. Result schema matches fetch_buoy_data() so the rest of
# the pipeline doesn't change.
# --------------------------------------------------------------------------

def fetch_aviationweather_metar(station_id: str, hours: int) -> list:
    """Fetch recent METARs from FAA aviationweather.gov. Up to ~168 hours."""
    hours = max(1, min(int(hours), 168))
    cache_key = f"avwx_{station_id}_{hours}h"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if datetime.utcnow().timestamp() - cached_time < CACHE_TTL_SECONDS:
            return cached_data

    url = (
        f"https://aviationweather.gov/api/data/metar"
        f"?ids={station_id}&format=json&hours={hours}&taf=false"
    )
    try:
        req = Request(url, headers={"User-Agent": "SailFrames/1.0"})
        with urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"aviationweather fetch failed for {station_id}: {e}")
        _cache[cache_key] = (datetime.utcnow().timestamp(), [])
        return []

    data = []
    for obs in payload or []:
        try:
            ts_unix = int(obs.get("obsTime", 0))
            if not ts_unix:
                continue
            ts = datetime.utcfromtimestamp(ts_unix)
            point = {
                "timestamp": ts.isoformat() + "Z",
                "unix_ts": ts_unix,
            }
            wdir = obs.get("wdir")
            if wdir is not None and wdir != "VRB":
                try:
                    point["wind_dir"] = float(wdir)
                except (ValueError, TypeError):
                    pass
            wspd = obs.get("wspd")
            if wspd is not None:
                try:
                    point["wind_speed_kts"] = round(float(wspd), 1)
                except (ValueError, TypeError):
                    pass
            wgst = obs.get("wgst")
            if wgst is not None:
                try:
                    point["wind_gust_kts"] = round(float(wgst), 1)
                except (ValueError, TypeError):
                    pass
            temp = obs.get("temp")
            if temp is not None:
                try:
                    point["air_temp_c"] = float(temp)
                except (ValueError, TypeError):
                    pass
            altim = obs.get("altim")  # already hPa per AviationWeather schema
            if altim is not None:
                try:
                    point["pressure_hpa"] = float(altim)
                except (ValueError, TypeError):
                    pass
            if "wind_dir" in point or "wind_speed_kts" in point:
                data.append(point)
        except Exception:
            continue

    data.sort(key=lambda x: x["unix_ts"])
    _cache[cache_key] = (datetime.utcnow().timestamp(), data)
    return data


def fetch_iowa_state_asos(station_id: str, start_ts: float, end_ts: float) -> list:
    """Fetch historical METARs from Iowa State Mesonet ASOS archive.
    Cache key is rounded to UTC date so two reloads of the same race
    share the same fetch."""
    start_dt = datetime.utcfromtimestamp(start_ts) - timedelta(hours=1)
    end_dt = datetime.utcfromtimestamp(end_ts) + timedelta(hours=1)
    cache_key = f"iastate_{station_id}_{start_dt.date()}_{end_dt.date()}"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        # 1-hour cache for archive data — it doesn't change frequently
        if datetime.utcnow().timestamp() - cached_time < 3600:
            return cached_data

    params = {
        "station": station_id,
        "data": "drct,sknt,gust,tmpf,alti",
        "year1": start_dt.year, "month1": start_dt.month, "day1": start_dt.day,
        "hour1": start_dt.hour, "minute1": start_dt.minute,
        "year2": end_dt.year, "month2": end_dt.month, "day2": end_dt.day,
        "hour2": end_dt.hour, "minute2": end_dt.minute,
        "tz": "Etc/UTC",
        "format": "onlycomma",
        "latlon": "no",
        "missing": "null",
        "trace": "null",
        "direct": "no",
        "report_type": "3,4",
    }
    url = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?" + urlencode(params)
    try:
        req = Request(url, headers={"User-Agent": "SailFrames/1.0"})
        with urlopen(req, timeout=20) as response:
            text = response.read().decode("utf-8")
    except Exception as e:
        logger.warning(f"Iowa State ASOS fetch failed for {station_id}: {e}")
        _cache[cache_key] = (datetime.utcnow().timestamp(), [])
        return []

    lines = text.strip().split("\n")
    if len(lines) < 2:
        _cache[cache_key] = (datetime.utcnow().timestamp(), [])
        return []
    header = [h.strip() for h in lines[0].split(",")]
    try:
        idx_valid = header.index("valid")
        idx_drct = header.index("drct")
        idx_sknt = header.index("sknt")
    except ValueError:
        _cache[cache_key] = (datetime.utcnow().timestamp(), [])
        return []
    idx_gust = header.index("gust") if "gust" in header else None
    idx_tmpf = header.index("tmpf") if "tmpf" in header else None
    idx_alti = header.index("alti") if "alti" in header else None

    def _f(parts, i):
        if i is None or i >= len(parts):
            return None
        s = parts[i].strip()
        if not s or s.lower() == "null" or s.lower() == "m":
            return None
        try:
            return float(s)
        except ValueError:
            return None

    data = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < len(header):
            continue
        try:
            ts = datetime.strptime(parts[idx_valid].strip(), "%Y-%m-%d %H:%M")
            point = {
                "timestamp": ts.isoformat() + "Z",
                "unix_ts": int(ts.timestamp()),
            }
            v = _f(parts, idx_drct)
            if v is not None: point["wind_dir"] = round(v, 0)
            v = _f(parts, idx_sknt)
            if v is not None: point["wind_speed_kts"] = round(v, 1)
            v = _f(parts, idx_gust)
            if v is not None: point["wind_gust_kts"] = round(v, 1)
            v = _f(parts, idx_tmpf)
            if v is not None: point["air_temp_c"] = round((v - 32) * 5 / 9, 1)
            v = _f(parts, idx_alti)
            if v is not None: point["pressure_hpa"] = round(v * 33.8639, 1)  # inHg → hPa
            if "wind_dir" in point or "wind_speed_kts" in point:
                data.append(point)
        except (ValueError, IndexError):
            continue

    data.sort(key=lambda x: x["unix_ts"])
    _cache[cache_key] = (datetime.utcnow().timestamp(), data)
    return data


def fetch_metar_data_for_timerange(station_id: str, start_ts: float, end_ts: float) -> list:
    """Tiered METAR fetch:
       1. aviationweather.gov for windows ending within the last 7 days
       2. Iowa State Mesonet ASOS archive for older windows or as fallback
       3. api.weather.gov as last resort if both above fail.

       METAR observations are hourly (at xx:54 typically). Short race
       windows (5-30 min) frequently contain ZERO METAR cycles, which
       makes the station look like it has no data. We buffer the filter
       by ±1h so the surrounding METARs are returned, letting the
       dashboard interpolate wind to the playback cursor and keeping the
       station in the wind-source picker."""
    METAR_BUFFER_S = 3600  # ±1 hour
    eff_start = start_ts - METAR_BUFFER_S
    eff_end = end_ts + METAR_BUFFER_S

    now = datetime.utcnow().timestamp()
    age_hours_start = (now - eff_start) / 3600

    # Tier 1: aviationweather.gov (fresh, fast)
    if age_hours_start <= 168:
        hours_back = max(2, int(age_hours_start) + 2)
        all_data = fetch_aviationweather_metar(station_id, hours_back)
        filtered = [d for d in all_data if eff_start <= d["unix_ts"] <= eff_end]
        if filtered:
            return filtered

    # Tier 2: Iowa State Mesonet (deep archive)
    all_data = fetch_iowa_state_asos(station_id, eff_start, eff_end)
    filtered = [d for d in all_data if eff_start <= d["unix_ts"] <= eff_end]
    if filtered:
        return filtered

    # Tier 3: api.weather.gov (last resort)
    if age_hours_start <= 168:
        all_data = fetch_nws_station_data(station_id, max(2, int(age_hours_start) + 1))
        return [d for d in all_data if eff_start <= d["unix_ts"] <= eff_end]

    return []


def fetch_synoptic_networks() -> dict:
    """Fetch the Synoptic mesonet network catalog once per container.
    Returns {mnet_id (int): shortname (str)}. Cached 24h since networks
    rarely change. Returns {} on any failure (the integration just shows
    "Synoptic" in the source column without the network suffix)."""
    if not SYNOPTIC_TOKEN:
        return {}
    cache_key = "synoptic_networks"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if datetime.utcnow().timestamp() - cached_time < 86400:
            return cached_data

    url = f"https://api.synopticdata.com/v2/networks?token={SYNOPTIC_TOKEN}"
    try:
        req = Request(url, headers={"User-Agent": "SailFrames/1.0"})
        with urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Synoptic networks fetch failed: {e}")
        _cache[cache_key] = (datetime.utcnow().timestamp(), {})
        return {}

    networks = {}
    for net in payload.get("MNET", []):
        try:
            nid = int(net.get("ID"))
            shortname = (net.get("SHORTNAME") or "").strip()
            if shortname:
                networks[nid] = shortname
        except (ValueError, TypeError):
            continue
    _cache[cache_key] = (datetime.utcnow().timestamp(), networks)
    logger.info(f"Synoptic networks cached: {len(networks)} entries")
    return networks


def fetch_synoptic_stations(start_ts: float, end_ts: float) -> dict:
    """Query Synoptic Mesonet for all stations with wind sensors in the
    Boston Harbor bbox over the requested window. Returns a dict shaped
    the same as get_all_buoys_data() so it can be merged in without
    touching the response schema. Silently returns {} if the token is
    missing or the API call fails — Synoptic is best-effort, NDBC + NWS
    remain the load-bearing sources."""
    if not SYNOPTIC_TOKEN:
        return {}

    cache_key = f"synoptic_{start_ts}_{end_ts}"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if datetime.utcnow().timestamp() - cached_time < CACHE_TTL_SECONDS:
            return cached_data

    # Synoptic timeseries endpoint. units=english returns wind in knots,
    # so we don't need m/s conversion.
    params = {
        "bbox": SYNOPTIC_BBOX,
        "start": datetime.utcfromtimestamp(start_ts).strftime("%Y%m%d%H%M"),
        "end": datetime.utcfromtimestamp(end_ts).strftime("%Y%m%d%H%M"),
        "vars": "wind_speed,wind_direction,wind_gust",
        "units": "english,speed|kts",
        "token": SYNOPTIC_TOKEN,
        "output": "json",
    }
    url = f"https://api.synopticdata.com/v2/stations/timeseries?{urlencode(params)}"

    try:
        req = Request(url, headers={"User-Agent": "SailFrames/1.0"})
        with urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Synoptic fetch failed: {e}")
        _cache[cache_key] = (datetime.utcnow().timestamp(), {})
        return {}

    summary = payload.get("SUMMARY", {})
    if summary.get("RESPONSE_CODE") not in (1, "1"):
        logger.warning(f"Synoptic non-OK response: {summary.get('RESPONSE_MESSAGE')}")
        _cache[cache_key] = (datetime.utcnow().timestamp(), {})
        return {}

    # Resolve MNET_ID → short name once for the whole batch
    networks_map = fetch_synoptic_networks()

    result = {}
    for station in payload.get("STATION", []):
        sid = station.get("STID")
        if not sid:
            continue
        prefix_id = f"SYN_{sid}"  # namespace to avoid collisions w/ NDBC ids

        obs = station.get("OBSERVATIONS", {}) or {}
        ts_list = obs.get("date_time", []) or []
        speed_key = next((k for k in obs.keys() if k.startswith("wind_speed_")), None)
        dir_key   = next((k for k in obs.keys() if k.startswith("wind_direction_")), None)
        gust_key  = next((k for k in obs.keys() if k.startswith("wind_gust_")), None)
        if not speed_key and not dir_key:
            continue

        speed_list = obs.get(speed_key, []) if speed_key else []
        dir_list   = obs.get(dir_key, []) if dir_key else []
        gust_list  = obs.get(gust_key, []) if gust_key else []

        data_points = []
        for i, ts_str in enumerate(ts_list):
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "").replace("+00:00", ""))
                point = {
                    "timestamp": ts.isoformat() + "Z",
                    "unix_ts": int(ts.timestamp()),
                }
                if i < len(speed_list) and speed_list[i] is not None:
                    point["wind_speed_kts"] = round(float(speed_list[i]), 1)
                if i < len(dir_list) and dir_list[i] is not None:
                    point["wind_dir"] = round(float(dir_list[i]), 0)
                if i < len(gust_list) and gust_list[i] is not None:
                    point["wind_gust_kts"] = round(float(gust_list[i]), 1)
                if "wind_speed_kts" in point or "wind_dir" in point:
                    data_points.append(point)
            except (ValueError, TypeError):
                continue

        if not data_points:
            continue

        try:
            lat = float(station.get("LATITUDE"))
            lon = float(station.get("LONGITUDE"))
        except (TypeError, ValueError):
            continue

        name = station.get("NAME") or sid
        network = ""
        # Synoptic returns MNET_ID as a numeric ID; resolve to a network
        # short name via the cached networks catalog.
        mnet_id = station.get("MNET_ID")
        try:
            nid = int(mnet_id)
            network = networks_map.get(nid, "")
        except (TypeError, ValueError):
            pass

        # Mark marine/sailing-center stations in a distinct color so they
        # stand out in the picker.
        is_marine_hint = any(h in name.lower() for h in SYNOPTIC_MARINE_HINTS)
        color = "#22d3ee" if is_marine_hint else "#a855f7"

        result[prefix_id] = {
            "station_id": prefix_id,
            "name": name,
            "lat": lat,
            "lon": lon,
            "type": "synoptic",
            "source": "synoptic",
            "network": network,
            "color": color,
            "data": ["wind"],
            "data_points": data_points,
            "has_data": True,
        }

    _cache[cache_key] = (datetime.utcnow().timestamp(), result)
    logger.info(f"Synoptic returned {len(result)} stations with wind data")
    return result


def get_all_buoys_data(start_ts: float, end_ts: float) -> dict:
    """Fetch data from all Boston Harbor weather stations for a time range."""
    result = {}

    for station_id, meta in BOSTON_BUOYS.items():
        source = meta.get("source", "ndbc")

        try:
            if source == "metar":
                data = fetch_metar_data_for_timerange(station_id, start_ts, end_ts)
            elif source == "nws":
                # legacy fallback if any station still uses the old source
                data = fetch_nws_data_for_timerange(station_id, start_ts, end_ts)
            else:
                data = fetch_buoy_data_for_timerange(station_id, start_ts, end_ts)
        except Exception as e:
            logger.warning(f"Error fetching {station_id}: {e}")
            data = []

        result[station_id] = {
            **meta,
            "station_id": station_id,
            "data_points": data,
            "has_data": len(data) > 0,
        }

    # Merge in Synoptic Mesonet stations (WeatherFlow Tempest, PWS, etc.)
    # IDs are namespaced "SYN_..." to avoid colliding with NDBC station IDs.
    try:
        synoptic_stations = fetch_synoptic_stations(start_ts, end_ts)
        for sid, sdata in synoptic_stations.items():
            if sid not in result:
                result[sid] = sdata
    except Exception as e:
        logger.warning(f"Synoptic merge failed: {e}")

    return result


def interpolate_buoy_value(data_points: list, target_ts: float, field: str) -> Optional[float]:
    """Interpolate a buoy value at a specific timestamp."""
    if not data_points:
        return None

    before = None
    after = None

    for point in data_points:
        if field not in point:
            continue
        if point["unix_ts"] <= target_ts:
            before = point
        elif point["unix_ts"] > target_ts and after is None:
            after = point
            break

    if before is None and after is None:
        return None
    if before is None:
        return after.get(field) if after else None
    if after is None:
        return before.get(field)

    t1, v1 = before["unix_ts"], before[field]
    t2, v2 = after["unix_ts"], after[field]

    if t2 == t1:
        return v1

    ratio = (target_ts - t1) / (t2 - t1)
    return round(v1 + ratio * (v2 - v1), 2)


def get_buoy_snapshot(buoys_data: dict, target_ts: float) -> dict:
    """Get interpolated buoy values at a specific timestamp."""
    snapshot = {}

    for station_id, buoy in buoys_data.items():
        data_points = buoy.get("data_points", [])

        snapshot[station_id] = {
            "station_id": station_id,
            "name": buoy["name"],
            "lat": buoy["lat"],
            "lon": buoy["lon"],
            "color": buoy["color"],
            "wind_dir": interpolate_buoy_value(data_points, target_ts, "wind_dir"),
            "wind_speed_kts": interpolate_buoy_value(data_points, target_ts, "wind_speed_kts"),
            "wind_gust_kts": interpolate_buoy_value(data_points, target_ts, "wind_gust_kts"),
            "wave_height_m": interpolate_buoy_value(data_points, target_ts, "wave_height_m"),
            "wave_period_sec": interpolate_buoy_value(data_points, target_ts, "wave_period_sec"),
            "pressure_hpa": interpolate_buoy_value(data_points, target_ts, "pressure_hpa"),
            "air_temp_c": interpolate_buoy_value(data_points, target_ts, "air_temp_c"),
            "water_temp_c": interpolate_buoy_value(data_points, target_ts, "water_temp_c"),
        }

        # Remove None values
        snapshot[station_id] = {k: v for k, v in snapshot[station_id].items() if v is not None}

    return snapshot
