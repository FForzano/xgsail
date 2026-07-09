"""
SailFrames Data Processing Lambda
Triggered by storage events on ``raw/uploads/{session_upload_id}/*.csv``
(docs/device-protocol.md layout). Downsamples sensor data, writes JSON to
``processed/uploads/{session_upload_id}/``, and reports results to the
backend system API (``BACKEND_CALLBACK_URL``) — the worker itself never
touches the DB. Session grouping/merging is the backend's job now (the
find-or-create logic in ``backend/services/ingestion.py``).
"""

import json
import os
import sys
import boto3
import csv
from io import StringIO
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Defensive csv reader config. The default field size limit is 128 KB,
# which a single corrupted nav.csv row (stray `"` from an SD bit-flip
# making the parser eat the rest of the file as one giant field) can
# easily exceed — that ate E1's 2026-05-25 race session: bit flip at
# byte 88295 ("2" → '"' in gps_date column) crashed process_gps with
# "field larger than field limit (131072)" and never produced gps.json
# / gps_10hz.json, breaking the race-day fleet view. maxsize defuses
# that specific failure; csv.QUOTE_NONE on every DictReader (see
# _csv_reader helper) prevents the quote-eats-everything pattern in
# the first place, since our nav/imu/wind/pres files never use quotes.
csv.field_size_limit(sys.maxsize)

def _csv_reader(content):
    """DictReader with quote handling disabled — single stray `"` won't
    consume the rest of the file. Use everywhere a CSV is parsed."""
    return csv.DictReader(StringIO(content), quoting=csv.QUOTE_NONE)

def _make_s3_client():
    """S3 client pointed at AWS S3 or, when SAILFRAMES_S3_ENDPOINT is set,
    a self-hosted MinIO (path-style addressing). Duplicated from
    backend/storage so the worker can stay self-contained."""
    endpoint = os.environ.get('SAILFRAMES_S3_ENDPOINT')
    if not endpoint:
        return boto3.client('s3')
    from botocore.config import Config
    return boto3.client(
        's3', endpoint_url=endpoint,
        config=Config(s3={'addressing_style': 'path'}),
    )


s3 = _make_s3_client()
DATA_BUCKET = os.environ.get('DATA_BUCKET', 'sailframes-fleet-data-prod')


def lambda_handler(event, context):
    """Process uploaded CSV files and create downsampled JSON.

    Processes each S3 record independently so one bad file doesn't block others.
    Failures are logged and collected, but don't prevent remaining files from processing.

    A record may also carry ``{"analyze": {"prefix": ...}, "bucket": ...}``
    instead of the usual S3 event shape — the backend dispatches that to run
    the analysis pipeline against an already-processed ``gps.json`` (manual
    imports), reusing this worker's numpy/pandas/``processing/*`` deps instead
    of duplicating them in the lean API container.
    """
    errors = []
    for record in event.get('Records', []):
        if 'analyze' in record:
            bucket = record.get('bucket', DATA_BUCKET)
            prefix = record['analyze']['prefix']
            logger.info(f"Analyzing {bucket}/{prefix}")
            try:
                process_analyze_prefix(bucket, prefix)
            except Exception as e:
                logger.error(f"Failed to analyze {prefix}: {e}", exc_info=True)
                errors.append({'key': prefix, 'error': str(e)})
            continue

        if 'activity_thumbnail' in record:
            bucket = record.get('bucket', DATA_BUCKET)
            activity_id = record['activity_thumbnail']['activity_id']
            prefixes = record['activity_thumbnail']['prefixes']
            logger.info(f"Rendering activity thumbnail for {activity_id} ({len(prefixes)} sessions)")
            try:
                process_activity_thumbnail(bucket, activity_id, prefixes)
            except Exception as e:
                logger.error(f"Failed to render activity thumbnail for {activity_id}: {e}", exc_info=True)
                errors.append({'key': activity_id, 'error': str(e)})
            continue

        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        logger.info(f"Processing {bucket}/{key}")

        try:
            process_file(bucket, key)
        except Exception as e:
            logger.error(f"Failed to process {key}: {e}", exc_info=True)
            errors.append({'key': key, 'error': str(e)})

    if errors:
        logger.error(f"Failed to process {len(errors)} of {len(event.get('Records', []))} files: {json.dumps(errors)}")
        return {'statusCode': 207, 'body': json.dumps({'errors': errors, 'message': f'{len(errors)} file(s) failed'})}

    return {'statusCode': 200, 'body': 'OK'}


def process_analyze_prefix(bucket: str, prefix: str):
    """Run the analysis pipeline against a processed upload prefix
    (``gps.json`` + optional ``imu``/``wind``/``pressure.json``) and write
    ``analysis.json`` back next to it.

    Dispatched by the backend after streams are registered (manual imports,
    or re-analysis of a device upload) — everything downstream of "we have a
    gps.json" reuses ``analyzer.analyze_session`` unchanged.
    """
    import tempfile
    from pathlib import Path

    from analyzer import analyze_session
    from thumbnail import render_track_thumbnail

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # wind_cache.json: the backend's pre-fetched regional wind, used as the
        # true-wind source when the session has no onboard wind sensor.
        for name in ('gps.json', 'imu.json', 'wind.json', 'pressure.json', 'wind_cache.json'):
            try:
                obj = s3.get_object(Bucket=bucket, Key=f"{prefix}{name}")
            except Exception:
                continue  # optional sensor file not present — analyzer tolerates missing files
            (tmp_path / name).write_bytes(obj['Body'].read())

        result = analyze_session(tmp_path)

        # Track-preview thumbnail for the sessions list — rendered once here
        # (not on every list load) and stored next to the rest of the
        # analysis output; the backend registers it as an `images` row.
        gps_path = tmp_path / 'gps.json'
        if gps_path.exists():
            try:
                png_bytes = render_track_thumbnail(json.loads(gps_path.read_text()))
                if png_bytes:
                    thumbnail_key = f"{prefix}thumbnail.png"
                    s3.put_object(Bucket=bucket, Key=thumbnail_key, Body=png_bytes,
                                  ContentType='image/png')
                    result['thumbnail_ref'] = thumbnail_key
            except Exception as e:
                logger.warning(f"Failed to render track thumbnail for {prefix}: {e}")

        # Estimated position/motion (see processing/track.py) get their own
        # blob artifacts — same reasoning as gps.json itself: thousands of
        # points per session, not something to inline into analysis.json or
        # the DB write below. Registered as session_streams so they're
        # discoverable later, same mechanism as every other sensor stream.
        streams = []
        for field, sensor_type in (('estimated_position', 'estimated_position'),
                                   ('estimated_motion', 'estimated_motion')):
            points = result.pop(field, None)
            if not points:
                continue
            key = f"{prefix}{sensor_type}.json"
            s3.put_object(Bucket=bucket, Key=key,
                          Body=json.dumps(points).encode(), ContentType='application/json')
            streams.append({
                'sensor_type': sensor_type, 'data_ref': key,
                'sample_rate_hz': None, 'row_count': len(points),
            })
        if streams:
            result['streams'] = streams

    s3.put_object(
        Bucket=bucket, Key=f"{prefix}analysis.json",
        Body=json.dumps(result, indent=2).encode(), ContentType='application/json',
    )

    # Persist the analysis to the DB (the backend fans it out to its normalized
    # tables). The prefix is processed/uploads/{upload_id}/ — key by that upload.
    upload_id = prefix.rstrip('/').split('/')[-1]
    _post_system(f"session-uploads/{upload_id}/analysis", result,
                 label=f"analysis for {upload_id}")


def process_activity_thumbnail(bucket: str, activity_id: str, prefixes: list):
    """Composite an overlay PNG — one track per session, different color each
    — from the already-processed ``gps.json`` of every session in the
    activity, and report it back to the backend.

    Dispatched by the backend whenever a session's analysis finishes (see
    ``backend/routers/system.py::upsert_session_analysis``), passing every
    sibling session's most recently processed prefix — not just the one that
    just finished, since the composite has to reflect the whole activity."""
    from thumbnail import render_overlay_thumbnail

    tracks = []
    for prefix in prefixes:
        try:
            obj = s3.get_object(Bucket=bucket, Key=f"{prefix}gps.json")
        except Exception:
            continue  # that session isn't processed yet — skip it, not fatal
        tracks.append(json.loads(obj['Body'].read()))

    png_bytes = render_overlay_thumbnail(tracks)
    if not png_bytes:
        return

    thumbnail_key = f"activities/{activity_id}/thumbnail.png"
    s3.put_object(Bucket=bucket, Key=thumbnail_key, Body=png_bytes, ContentType='image/png')
    _post_system(f"activities/{activity_id}/thumbnail", {"thumbnail_ref": thumbnail_key},
                 label=f"activity thumbnail for {activity_id}")


def extract_start_time_from_filename(filename: str) -> str:
    """Extract start time (HHMMSS) from E1 filename.

    E1 filenames: E1_boot24_163325_nav.csv or E1_20260402_163325_nav.csv
    Returns HHMMSS string (e.g., '163325') or empty string if not found.
    """
    import re
    # Match 6 digits that look like a time (HHMMSS)
    # In E1_boot24_163325_nav.csv, the time is the third part
    parts = filename.replace('.csv', '').split('_')
    for part in parts:
        if len(part) == 6 and part.isdigit():
            # Validate it looks like a time (HH < 24, MM < 60, SS < 60)
            hh, mm, ss = int(part[:2]), int(part[2:4]), int(part[4:6])
            if hh < 24 and mm < 60 and ss < 60:
                return part
    return ''



def _extract_date_from_filename(filename: str) -> str:
    """``E1_20260701_163325_nav.csv`` → ``2026-07-01`` (fallback date anchor
    for corruption filtering in process_gps)."""
    parts = filename.split('_')
    if len(parts) >= 2 and len(parts[1]) == 8 and parts[1].isdigit():
        d = parts[1]
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    return None


def _sensor_from_filename(filename: str) -> str:
    if '_nav.csv' in filename:
        return 'gps'
    if '_imu.csv' in filename:
        return 'imu'
    if '_pressure.csv' in filename or '_pres.csv' in filename or '_baro.csv' in filename:
        return 'pressure'
    if '_wind.csv' in filename:
        return 'wind'
    return None


def _post_system(path: str, payload: dict, label: str):
    """POST a JSON payload to a backend system API path (3 attempts).

    Workers are DB-blind by design: the backend owns every DB write. When
    BACKEND_CALLBACK_URL is unset the worker runs in pure-storage mode and
    skips the callback silently. ``path`` is relative to ``/api/system/``."""
    base = os.environ.get('BACKEND_CALLBACK_URL')
    token = os.environ.get('SAILFRAMES_HOOK_TOKEN')
    if not base or not token:
        logger.info("BACKEND_CALLBACK_URL/hook token unset - skipping callback")
        return
    import time
    import urllib.request

    url = f"{base.rstrip('/')}/api/system/{path.lstrip('/')}"
    body = json.dumps(payload).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, data=body, method='POST',
                headers={'Content-Type': 'application/json',
                         'Authorization': f'Bearer {token}'},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                logger.info(f"Callback OK ({resp.status}) for {label}")
                return
        except Exception as e:
            logger.warning(f"Callback attempt {attempt + 1}/3 failed: {e}")
            time.sleep(2 ** attempt)
    logger.error(f"Callback permanently failed for {label}")


def _post_callback(payload: dict):
    """Report file-processing results to the backend ingest-complete endpoint."""
    _post_system("ingest/complete", payload,
                 label=str(payload.get('session_upload_id')))


def process_file(bucket: str, key: str):
    """Process one file of a device upload bundle.

    Only the protocol path shape is supported (docs/device-protocol.md):
    ``raw/uploads/{session_upload_id}/{filename}`` — the session_upload row
    already exists (created by the device API or an import), so there is no
    folder/date/merge heuristics: output goes to
    ``processed/uploads/{session_upload_id}/{sensor}.json`` and the results
    are reported to the backend callback, which owns the DB.
    """
    parts = key.split('/')
    if len(parts) != 4 or parts[0] != 'raw' or parts[1] != 'uploads':
        logger.warning(f"Ignoring key outside the upload layout: {key}")
        return
    upload_id = parts[2]
    filename = parts[3]

    sensor_type = _sensor_from_filename(filename)
    if sensor_type is None:
        logger.warning(f"Unknown sensor file type, ignoring: {filename}")
        return

    date = _extract_date_from_filename(filename)
    start_time = extract_start_time_from_filename(filename)

    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        # errors='replace': SD/firmware corruption occasionally injects a
        # non-UTF8 byte mid-file; losing one row beats losing the session.
        csv_content = response['Body'].read().decode('utf-8', errors='replace')

        data_10hz = None
        if sensor_type == 'gps':
            data, data_10hz, _actual_date, _drops = process_gps(csv_content, date, start_time)
        elif sensor_type == 'imu':
            data = process_imu(csv_content, date, start_time)
        elif sensor_type == 'pressure':
            data = process_pressure(csv_content, date, start_time)
        else:
            data = process_wind(csv_content, date, start_time)
    except Exception as e:
        _post_callback({
            'session_upload_id': upload_id,
            'status': 'failed',
            'error': str(e),
            'streams': [],
        })
        raise

    prefix = f"processed/uploads/{upload_id}/"
    output_key = f"{prefix}{sensor_type}.json"

    # Merge with anything already processed for this upload (a bundle may
    # contain several files of the same sensor): dedupe by timestamp, sort.
    existing_data = []
    try:
        existing = s3.get_object(Bucket=bucket, Key=output_key)
        existing_data = json.loads(existing['Body'].read().decode('utf-8'))
    except Exception:
        pass
    seen = set()
    merged = []
    for item in existing_data + data:
        t = item.get('t', '')
        if t and t not in seen:
            seen.add(t)
            merged.append(item)
    merged.sort(key=lambda x: x.get('t', ''))

    s3.put_object(Bucket=bucket, Key=output_key,
                  Body=json.dumps(merged, default=str), ContentType='application/json')
    logger.info(f"Wrote {len(merged)} records to {output_key}")

    if sensor_type == 'gps' and data_10hz:
        key_10hz = f"{prefix}gps_10hz.json"
        existing_10hz = []
        try:
            existing = s3.get_object(Bucket=bucket, Key=key_10hz)
            existing_10hz = json.loads(existing['Body'].read().decode('utf-8'))
        except Exception:
            pass
        seen = set()
        merged_10hz = []
        for item in existing_10hz + data_10hz:
            t = item.get('t', '')
            if t and t not in seen:
                seen.add(t)
                merged_10hz.append(item)
        merged_10hz.sort(key=lambda x: x.get('t', ''))
        s3.put_object(Bucket=bucket, Key=key_10hz,
                      Body=json.dumps(merged_10hz, default=str), ContentType='application/json')

    _post_callback({
        'session_upload_id': upload_id,
        'status': 'processed',
        'start_time': merged[0]['t'] if merged else None,
        'end_time': merged[-1]['t'] if merged else None,
        'streams': [{
            'sensor_type': sensor_type,
            'data_ref': output_key,
            'sample_rate_hz': 1.0,
            'row_count': len(merged),
        }],
    })


def extract_gps_date_from_csv(csv_content: str) -> str:
    """Extract the actual UTC date from GPS CSV data.

    E1 CSV has 'gps_date' column in DDMMYY format (e.g., "040426" for 2026-04-04).
    Falls back to None if not found.

    Returns: Date string in YYYY-MM-DD format, or None
    """
    reader = _csv_reader(csv_content)
    for row in reader:
        gps_date = row.get('gps_date', '')
        if gps_date and len(gps_date) == 6:
            try:
                # Parse DDMMYY format
                day = int(gps_date[:2])
                month = int(gps_date[2:4])
                year = 2000 + int(gps_date[4:6])  # Assumes 20xx
                if 1 <= day <= 31 and 1 <= month <= 12:
                    return f"{year}-{month:02d}-{day:02d}"
            except ValueError:
                pass
    return None


# GPS fix quality/plausibility gate shared by both the 10Hz and 1Hz E1 passes
# below — kept in one place so the two passes can never drift apart (they
# used to duplicate this inline).
E1_LATLON_SANITY_DEG = 1.0


def _e1_row_fields(row: dict) -> "Optional[dict]":
    """Extract + validate one E1-format CSV row's GPS fields (fix/lat/lon/hdop
    sanity gate). Raises ``(ValueError, TypeError)`` if a field can't even be
    parsed (bit-flip corruption) — the caller counts that as a drop. Returns
    ``None`` (not counted, just silently skipped) if the row parses fine but
    fails the fix/hdop/coordinate sanity gate — same distinction the
    pre-dedup code made."""
    fix = int(row.get('fix', 0) or 0)
    lat = float(row.get('lat', 0) or 0)
    lon = float(row.get('lon', 0) or 0)
    hdop = float(row.get('hdop', 99) or 99)
    if not (fix >= 1 and abs(lat) > E1_LATLON_SANITY_DEG and abs(lon) > E1_LATLON_SANITY_DEG
            and hdop < 10):
        return None
    return {
        'lat': lat,
        'lon': lon,
        'speed_kn': round(float(row.get('sog', 0) or 0), 2),
        'course': round(float(row.get('cog', 0) or 0), 1),
        'fix': fix,
        'sats': int(row.get('sat', 0) or 0),
        'hdop': round(hdop, 1),
    }


def _s1_row_fields(row: dict) -> dict:
    """Extract one S1-format CSV row's GPS fields — no validity gate today
    (unlike E1, S1 rows are trusted as-is)."""
    return {
        'lat': float(row.get('latitude', 0) or 0),
        'lon': float(row.get('longitude', 0) or 0),
        'speed_kn': round(float(row.get('speed_knots', 0) or 0), 2),
        'course': round(float(row.get('course_deg', 0) or 0), 1),
        'fix': int(row.get('fix_quality', 0) or 0),
        'sats': int(row.get('satellites', 0) or 0),
    }


def process_gps(csv_content: str, date: str = None, start_time: str = None) -> tuple:
    """Downsample GPS from 10Hz to 1Hz, keeping max speed per second.
    Also generates full 10Hz data for high-resolution track display.

    Supports two CSV formats:
    - S1: utc_time,latitude,longitude,speed_knots,course_deg,fix_quality,satellites
    - E1: ms,utc,lat,lon,alt,sog,cog,sat,hdop,fix,gps_date

    Args:
        csv_content: CSV data as string
        date: Date string (YYYY-MM-DD) for E1 timestamp generation (fallback)
        start_time: Start time (HHMMSS) from filename for old E1 format

    Returns:
        Tuple of (data_1hz, data_10hz, actual_gps_date) where actual_gps_date may differ
        from the input date if GPS data contains a different date.
    """
    from datetime import timedelta

    reader = _csv_reader(csv_content)
    rows = list(reader)
    if not rows:
        return [], [], date

    # Detect format based on column names
    first_row = rows[0]
    is_e1_format = 'utc' in first_row and 'lat' in first_row

    # Extract actual GPS date from E1 data if available
    actual_date = date
    if is_e1_format:
        # Re-parse to extract date from gps_date column
        gps_date = extract_gps_date_from_csv(csv_content)
        if gps_date:
            if gps_date != date:
                logger.info(f"GPS date {gps_date} differs from path date {date}, using GPS date")
            actual_date = gps_date

    # Compute the session start anchor from the filename. ANY row
    # that parses to a timestamp >5 min BEFORE this anchor is
    # bit-flip corruption (the only way for gps_date+utc to combine
    # into a pre-session timestamp is if one of them got flipped).
    # 5-min buffer absorbs GPS-warmup clock jitter.
    # E1's 2026-05-25 race: filename says session started 21:16:27,
    # but a row with gps_date corrupted "260526"→"250526" (single
    # bit-flip on byte 0x36→0x35) combined with real utc "000235"
    # parsed as 2026-05-25T00:02:35Z, ~21 hours before session
    # start, poisoning manifest start_time and shifting the session
    # into the wrong day on the dashboard.
    session_start_anchor = None
    if is_e1_format and start_time and len(start_time) == 6 and start_time.isdigit():
        try:
            anchor_dt = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H%M%S")
            anchor_dt = anchor_dt - timedelta(minutes=5)
            session_start_anchor = anchor_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass

    # Time correction only for S1 (Pi5 clock was ~41 minutes ahead)
    TIME_CORRECTION_SECONDS = 0 if is_e1_format else -2460

    # Collect all valid records for 10Hz output and group by second for 1Hz
    all_valid_records = []  # Full 10Hz data
    by_second = defaultdict(list)  # Grouped for 1Hz downsampling

    # SD card health: per-category corruption counters. Each tracks one
    # specific bit-flip / write-corruption signature. Surfaced via the
    # fleet dashboard's SD Health column so an aging card shows up
    # before it costs a race day.
    drops = {
        'bad_gps_date': 0,        # length != 6 or non-digit (NUL/space/etc.)
        'pre_session_anchor': 0,  # timestamp >5 min before filename start
        'row_convert_error': 0,   # int/float ValueError on fix/lat/lon/hdop
        'latlon_outlier': 0,      # post-pass median filter (>1° from session center)
    }

    for row in rows:
        if is_e1_format:
            # E1 format: utc is HHMMSS.mmm (e.g., "123756.100")
            utc_raw = row.get('utc', '')
            if not utc_raw:
                continue

            # Per-row date. UTC midnight rollover inside a single
            # session would otherwise mis-date the post-midnight rows
            # back to the start-of-session day — that bug stamped the
            # 2026-05-12 235632 session with start=00:00:00 /
            # end=23:59:59, which then silently swallowed every later
            # upload via the session-merge overlap path.
            #
            # If the gps_date column is corrupted (length != 6 or
            # unparseable), DROP THE ROW rather than falling back to
            # actual_date — for a row past UTC midnight the fallback
            # produces a timestamp 24 hours BEFORE the row's real time
            # and poisons the session start_time. E1's 2026-05-25 race
            # had 55 such rows; one survivor stamped at
            # 2026-05-25T00:02:10Z (real time ~2026-05-26T00:02:10Z)
            # made the session group under May 24 on the dashboard.
            # Strict: gps_date must be exactly 6 ASCII digits. Strip
            # before checking (some corrupted rows have trailing
            # whitespace), then isdigit() rejects anything with
            # embedded space/punctuation/NUL — necessary because
            # Python's int(" 5") silently strips whitespace and would
            # otherwise let "25 526" (NUL-corrupted) parse as a
            # valid date and poison the timestamp.
            row_gps_date = (row.get('gps_date') or '').strip()
            if len(row_gps_date) != 6 or not row_gps_date.isdigit():
                drops['bad_gps_date'] += 1
                continue
            try:
                d = int(row_gps_date[:2])
                m = int(row_gps_date[2:4])
                y = 2000 + int(row_gps_date[4:6])
                if not (1 <= d <= 31 and 1 <= m <= 12):
                    drops['bad_gps_date'] += 1
                    continue
                row_date = f"{y}-{m:02d}-{d:02d}"
            except ValueError:
                drops['bad_gps_date'] += 1
                continue

            try:
                # Parse HHMMSS.mmm format
                utc_float = float(utc_raw)
                hours = int(utc_float // 10000)
                minutes = int((utc_float % 10000) // 100)
                seconds = int(utc_float % 100)
                millis = int((utc_float % 1) * 1000)
                # Full timestamp with milliseconds for 10Hz
                full_ts = f"{row_date}T{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}Z"
                # Second-only timestamp for grouping
                second = f"{row_date}T{hours:02d}:{minutes:02d}:{seconds:02d}"
            except ValueError:
                continue

            # Cross-check: row timestamps must be at or after the
            # filename-derived session start (with 5-min buffer).
            # ISO 8601 strings sort correctly so string compare is safe.
            if session_start_anchor and full_ts < session_start_anchor:
                drops['pre_session_anchor'] += 1
                continue

            # Filter out invalid GPS records. Per-row try/except so a
            # single bit-flip-corrupted row (e.g. lat='42"1.561071')
            # skips cleanly instead of aborting the whole file. E1's
            # 2026-05-25 race had 6 such rows out of ~100k — without
            # this, conversion ValueError swallowed the entire session.
            try:
                fields = _e1_row_fields(row)
            except (ValueError, TypeError):
                drops['row_convert_error'] += 1
                continue
            if fields is None:
                continue
            all_valid_records.append({'t': full_ts, **fields})
            by_second[second].append(row)
        else:
            # S1 format: utc_time is ISO timestamp
            ts = row.get('utc_time', '')
            if not ts:
                continue
            try:
                dt = datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')
                dt_corrected = dt + timedelta(seconds=TIME_CORRECTION_SECONDS)
                second = dt_corrected.strftime('%Y-%m-%dT%H:%M:%S')
                # Include milliseconds if present
                if len(ts) > 19 and '.' in ts:
                    millis = ts[20:23] if len(ts) > 22 else ts[20:]
                    full_ts = dt_corrected.strftime('%Y-%m-%dT%H:%M:%S') + '.' + millis + 'Z'
                else:
                    full_ts = second + 'Z'
            except ValueError:
                second = ts[:19]
                full_ts = second + 'Z'

            all_valid_records.append({'t': full_ts, **_s1_row_fields(row)})
            by_second[second].append(row)

    # Sort 10Hz data by timestamp
    all_valid_records.sort(key=lambda x: x['t'])

    # Lat/lon outlier filter — catches rows where date+time+gps_date
    # are all valid but lat or lon has a single-bit corruption that
    # makes the value numerically plausible but geographically far
    # from the rest of the session (e.g. leading "4" of 42.x dropped
    # to "2.x", or sign of -71.x lost to 71.x).
    # Threshold of 1° is generous: ~111 km lat / ~85 km lon at this
    # latitude. A real sailing session typically covers <30 km; the
    # observed corruption produces values >5° from median. 1° is well
    # inside the corruption gap and well outside any legitimate sail.
    # Anchor is the median of records that passed all earlier filters,
    # so it's robust to up to ~50% corrupted rows (which we'll never
    # see — observed corruption rate is <0.1%).
    LATLON_OUTLIER_DEG = 1.0
    median_lat = None
    median_lon = None
    if is_e1_format and len(all_valid_records) >= 10:
        lats_sorted = sorted(r['lat'] for r in all_valid_records)
        lons_sorted = sorted(r['lon'] for r in all_valid_records)
        median_lat = lats_sorted[len(lats_sorted) // 2]
        median_lon = lons_sorted[len(lons_sorted) // 2]
        pre = len(all_valid_records)
        all_valid_records = [
            r for r in all_valid_records
            if abs(r['lat'] - median_lat) <= LATLON_OUTLIER_DEG
            and abs(r['lon'] - median_lon) <= LATLON_OUTLIER_DEG
        ]
        dropped = pre - len(all_valid_records)
        drops['latlon_outlier'] = dropped
        if dropped > 0:
            logger.info(
                f"Filtered {dropped} GPS outlier rows (>{LATLON_OUTLIER_DEG}° "
                f"from median {median_lat:.4f},{median_lon:.4f})"
            )

    # Take sample with max speed per second for 1Hz output
    result_1hz = []
    for second, samples in sorted(by_second.items()):
        if is_e1_format:
            # Every row here already passed _e1_row_fields once in the 10Hz
            # pass above (that's how it got into by_second) — re-extract
            # (cheap) rather than re-deriving the same fields a third way,
            # then apply the same outlier filter as the 10Hz path.
            valid_fields = []
            for s in samples:
                fields = _e1_row_fields(s)
                if fields is None:
                    continue
                if median_lat is not None and (
                    abs(fields['lat'] - median_lat) > LATLON_OUTLIER_DEG
                    or abs(fields['lon'] - median_lon) > LATLON_OUTLIER_DEG
                ):
                    continue
                valid_fields.append(fields)
            if not valid_fields:
                continue
            best = max(valid_fields, key=lambda f: f['speed_kn'])
        else:
            best = max((_s1_row_fields(s) for s in samples), key=lambda f: f['speed_kn'])
        result_1hz.append({'t': second + 'Z', **best})

    drops['total_input_rows'] = len(rows)
    drops['kept_10hz_rows'] = len(all_valid_records)
    return result_1hz, all_valid_records, actual_date, drops


def process_imu(csv_content: str, date: str = None, start_time: str = None) -> list:
    """Downsample IMU from 50Hz to 1Hz, averaging values.

    Supports two CSV formats:
    - S1: utc_time,heel_deg,pitch_deg,heading_deg,accel_x_mps2,accel_y_mps2,accel_z_mps2
    - E1 (new): ms,utc,ax,ay,az,gx,gy,gz,heel,pitch
    - E1 (old): ms,ax,ay,az,gx,gy,gz,heel,pitch

    Args:
        csv_content: CSV data as string
        date: Date string (YYYY-MM-DD) for E1 timestamp generation
        start_time: Start time (HHMMSS) from filename for old E1 format
    """
    from datetime import timedelta

    reader = _csv_reader(csv_content)
    rows = list(reader)
    if not rows:
        return []

    # Detect format based on column names
    first_row = rows[0]
    is_e1_format = 'ms' in first_row and 'ax' in first_row
    has_utc = 'utc' in first_row  # New E1 format with GPS time

    # Time correction only for S1 (Pi5 clock was ~41 minutes ahead)
    TIME_CORRECTION_SECONDS = 0 if is_e1_format else -2460

    # Parse start_time for old E1 format
    base_seconds = 0
    if start_time and len(start_time) == 6:
        base_seconds = int(start_time[:2]) * 3600 + int(start_time[2:4]) * 60 + int(start_time[4:6])

    # Group by second
    by_second = defaultdict(list)
    for row in rows:
        if is_e1_format:
            if has_utc:
                # New E1 format: utc is HHMMSS.mmm from GPS
                utc_raw = row.get('utc', '')
                if not utc_raw:
                    continue
                try:
                    utc_float = float(utc_raw)
                    hours = int(utc_float // 10000)
                    minutes = int((utc_float % 10000) // 100)
                    seconds = int(utc_float % 100)
                    second = f"{date}T{hours:02d}:{minutes:02d}:{seconds:02d}"
                except ValueError:
                    continue
            else:
                # Old E1 format: ms is milliseconds since boot, add to start_time from filename
                ms = row.get('ms', '')
                if not ms:
                    continue
                try:
                    sec_offset = int(float(ms) // 1000)
                    total_sec = base_seconds + sec_offset
                    hours = (total_sec // 3600) % 24
                    minutes = (total_sec % 3600) // 60
                    secs = total_sec % 60
                    second = f"{date}T{hours:02d}:{minutes:02d}:{secs:02d}"
                except ValueError:
                    continue
        else:
            # S1 format: utc_time is ISO timestamp
            ts = row.get('utc_time', '')
            if not ts:
                continue
            try:
                dt = datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')
                dt_corrected = dt + timedelta(seconds=TIME_CORRECTION_SECONDS)
                second = dt_corrected.strftime('%Y-%m-%dT%H:%M:%S')
            except ValueError:
                second = ts[:19]

        by_second[second].append(row)

    # Average values per second
    result = []
    for second, samples in sorted(by_second.items()):
        n = len(samples)
        avg = lambda field: sum(float(r.get(field, 0) or 0) for r in samples) / n

        if is_e1_format:
            # E1 has heel, pitch, and heading directly, ax/ay/az for accel, gx/gy/gz for gyro
            # Additional fields added in firmware v2.5+:
            # - lax/lay/laz: linear acceleration (gravity removed) for impact detection
            # - stability: motion classifier (0=Unknown,1=OnTable,2=Stationary,3=Stable,4=Motion)
            # - accuracy: rotation vector calibration quality (0-3, 3=highest)
            heading_val = avg('heading') if 'heading' in samples[0] else 0
            gyro_x = avg('gx') if 'gx' in samples[0] else 0
            gyro_y = avg('gy') if 'gy' in samples[0] else 0
            gyro_z = avg('gz') if 'gz' in samples[0] else 0
            linaccel_x = avg('lax') if 'lax' in samples[0] else 0
            linaccel_y = avg('lay') if 'lay' in samples[0] else 0
            linaccel_z = avg('laz') if 'laz' in samples[0] else 0
            mag_x = avg('mx') if 'mx' in samples[0] else 0
            mag_y = avg('my') if 'my' in samples[0] else 0
            mag_z = avg('mz') if 'mz' in samples[0] else 0
            # For stability, take the mode (most common value) not average
            stability_vals = [int(r.get('stability', 0) or 0) for r in samples]
            stability = max(set(stability_vals), key=stability_vals.count) if stability_vals else 0
            # For accuracy, take the minimum (worst case in the second)
            accuracy_vals = [int(r.get('accuracy', 0) or 0) for r in samples]
            accuracy = min(accuracy_vals) if accuracy_vals else 0
            result.append({
                't': second + 'Z',
                'heel': round(avg('heel'), 1),
                'pitch': round(avg('pitch'), 1),
                'heading': round(heading_val, 1),
                'accel_x': round(avg('ax'), 2),
                'accel_y': round(avg('ay'), 2),
                'accel_z': round(avg('az'), 2),
                'gyro_x': round(gyro_x, 1),  # Roll rate (deg/s)
                'gyro_y': round(gyro_y, 1),  # Pitch rate (deg/s)
                'gyro_z': round(gyro_z, 1),  # Yaw/turn rate (deg/s) - key for maneuver detection
                'linaccel_x': round(linaccel_x, 3),  # Linear accel X (no gravity)
                'linaccel_y': round(linaccel_y, 3),  # Linear accel Y (no gravity)
                'linaccel_z': round(linaccel_z, 3),  # Linear accel Z (no gravity)
                'mag_x': round(mag_x, 1),  # Magnetic field X (uT)
                'mag_y': round(mag_y, 1),  # Magnetic field Y (uT)
                'mag_z': round(mag_z, 1),  # Magnetic field Z (uT)
                'stability': stability,  # Motion state classifier
                'accuracy': accuracy,    # Rotation vector calibration quality
            })
        else:
            # S1 format with corrections for mounting orientation
            # Heading correction: IMU mounted 180° (X-axis toward stern)
            raw_heading = avg('heading_deg')
            corrected_heading = (raw_heading + 180) % 360

            # Heel correction: IMU mounted 90° off
            raw_heel = avg('heel_deg')
            corrected_heel = raw_heel + 90

            result.append({
                't': second + 'Z',
                'heel': round(corrected_heel, 1),
                'pitch': round(avg('pitch_deg'), 1),
                'heading': round(corrected_heading, 1),
                'accel_x': round(avg('accel_x_mps2'), 2),
                'accel_y': round(avg('accel_y_mps2'), 2),
                'accel_z': round(avg('accel_z_mps2'), 2)
            })

    return result


def process_pressure(csv_content: str, date: str = None, start_time: str = None) -> list:
    """Process pressure data (already 1Hz, minimal transformation).

    Supports two CSV formats:
    - S1: utc_time,pressure_hpa,temperature_c,pressure_trend
    - E1: ms,utc,pressure_hpa,temp_c,pres_min,pres_max

    Args:
        csv_content: CSV data as string
        date: Date string (YYYY-MM-DD) for E1 timestamp generation
        start_time: Start time (HHMMSS) from filename for old E1 format
    """
    from datetime import timedelta

    reader = _csv_reader(csv_content)
    rows = list(reader)
    if not rows:
        return []

    # Detect format based on column names
    first_row = rows[0]
    is_e1_format = 'ms' in first_row
    has_utc = 'utc' in first_row

    # Time correction only for S1 (Pi5 clock was ~41 minutes ahead)
    TIME_CORRECTION_SECONDS = 0 if is_e1_format else -2460

    # Parse start_time for old E1 format
    base_seconds = 0
    if start_time and len(start_time) == 6:
        base_seconds = int(start_time[:2]) * 3600 + int(start_time[2:4]) * 60 + int(start_time[4:6])

    if is_e1_format:
        by_second = defaultdict(list)
        for row in rows:
            if has_utc:
                utc_raw = row.get('utc', '')
                if not utc_raw:
                    continue
                try:
                    utc_float = float(utc_raw)
                    hours = int(utc_float // 10000)
                    minutes = int((utc_float % 10000) // 100)
                    seconds = int(utc_float % 100)
                    second = f"{date}T{hours:02d}:{minutes:02d}:{seconds:02d}"
                except ValueError:
                    continue
            else:
                ms = row.get('ms', '')
                if not ms:
                    continue
                try:
                    sec_offset = int(float(ms) // 1000)
                    total_sec = base_seconds + sec_offset
                    hours = (total_sec // 3600) % 24
                    minutes = (total_sec % 3600) // 60
                    seconds = total_sec % 60
                    second = f"{date}T{hours:02d}:{minutes:02d}:{seconds:02d}"
                except ValueError:
                    continue
            by_second[second].append(row)

        result = []
        for second, samples in sorted(by_second.items()):
            best = samples[-1]
            result.append({
                't': second + 'Z',
                'hpa': round(float(best.get('pressure_hpa', 0) or 0), 1),
                'temp_c': round(float(best.get('temp_c', 0) or 0), 1),
            })
        return result
    else:
        # S1 format
        result = []
        for row in rows:
            ts = row.get('utc_time', '')
            if not ts:
                continue

            try:
                dt = datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')
                dt_corrected = dt + timedelta(seconds=TIME_CORRECTION_SECONDS)
                corrected_ts = dt_corrected.strftime('%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                corrected_ts = ts[:19] + 'Z'

            result.append({
                't': corrected_ts,
                'hpa': round(float(row.get('pressure_hpa', 0) or 0), 1),
                'temp_c': round(float(row.get('temperature_c', 0) or 0), 1),
                'trend': row.get('pressure_trend', '')
            })

        return result


def process_wind(csv_content: str, date: str = None, start_time: str = None) -> list:
    """Process wind data (already 1Hz, minimal transformation).

    Supports two CSV formats:
    - S1: utc_time,apparent_wind_speed_knots,apparent_wind_angle_deg,compass_heading_deg
    - E1 (new): ms,utc,aws_kts,aws_mps,awa_deg,battery
    - E1 (old): ms,aws_kts,aws_mps,awa_deg,battery

    Args:
        csv_content: CSV data as string
        date: Date string (YYYY-MM-DD) for E1 timestamp generation
        start_time: Start time (HHMMSS) from filename for old E1 format
    """
    from datetime import timedelta

    reader = _csv_reader(csv_content)
    rows = list(reader)
    if not rows:
        return []

    # Detect format based on column names
    first_row = rows[0]
    is_e1_format = 'ms' in first_row and 'aws_kts' in first_row
    has_utc = 'utc' in first_row  # New E1 format with GPS time

    # Time correction only for S1 (Pi5 clock was ~41 minutes ahead)
    TIME_CORRECTION_SECONDS = 0 if is_e1_format else -2460

    # Parse start_time for old E1 format
    base_seconds = 0
    if start_time and len(start_time) == 6:
        base_seconds = int(start_time[:2]) * 3600 + int(start_time[2:4]) * 60 + int(start_time[4:6])

    # Group by second for E1 (may have multiple samples)
    if is_e1_format:
        by_second = defaultdict(list)
        for row in rows:
            if has_utc:
                # New E1 format: utc is HHMMSS.mmm from GPS
                utc_raw = row.get('utc', '')
                if not utc_raw:
                    continue
                try:
                    utc_float = float(utc_raw)
                    hours = int(utc_float // 10000)
                    minutes = int((utc_float % 10000) // 100)
                    seconds = int(utc_float % 100)
                    second = f"{date}T{hours:02d}:{minutes:02d}:{seconds:02d}"
                except ValueError:
                    continue
            else:
                # Old E1 format: ms is milliseconds since boot, add to start_time from filename
                ms = row.get('ms', '')
                if not ms:
                    continue
                try:
                    sec_offset = int(float(ms) // 1000)
                    total_sec = base_seconds + sec_offset
                    hours = (total_sec // 3600) % 24
                    minutes = (total_sec % 3600) // 60
                    seconds = total_sec % 60
                    second = f"{date}T{hours:02d}:{minutes:02d}:{seconds:02d}"
                except ValueError:
                    continue
            by_second[second].append(row)

        result = []
        for second, samples in sorted(by_second.items()):
            # Take last sample per second (most recent)
            best = samples[-1]
            result.append({
                't': second + 'Z',
                'aws_kn': round(float(best.get('aws_kts', 0) or 0), 1),
                'awa': round(float(best.get('awa_deg', 0) or 0), 0),
                'heading': 0  # E1 wind sensor doesn't provide heading
            })
        return result
    else:
        # S1 format
        result = []
        for row in rows:
            ts = row.get('utc_time', '')
            if not ts:
                continue

            # Apply time correction
            try:
                dt = datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')
                dt_corrected = dt + timedelta(seconds=TIME_CORRECTION_SECONDS)
                corrected_ts = dt_corrected.strftime('%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                corrected_ts = ts[:19] + 'Z'

            result.append({
                't': corrected_ts,
                'aws_kn': round(float(row.get('apparent_wind_speed_knots', 0) or 0), 1),
                'awa': round(float(row.get('apparent_wind_angle_deg', 0) or 0), 0),
                'heading': round((float(row.get('compass_heading_deg', 0) or 0) + 180) % 360, 1)
            })

        return result


