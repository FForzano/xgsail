#!/usr/bin/env python3
"""
Restore S1 (sailframes-01) sessions by processing raw CSV files locally.
Splits into separate sessions based on 10-minute GPS time gaps.

Usage:
    python scripts/restore_s1_sessions.py
    python scripts/restore_s1_sessions.py --dry-run
"""

import argparse
import boto3
import csv
import json
from io import StringIO
from datetime import datetime, timezone, timedelta
from collections import defaultdict

DATA_BUCKET = 'sailframes-fleet-data-prod'
SESSION_GAP_MINUTES = 10  # Split sessions if gap > 10 minutes


def list_raw_files(s3, device_id: str, date: str):
    """List all raw CSV files for a device/date."""
    prefix = f"raw/{device_id}/{date}/"
    files = {'gps': [], 'imu': [], 'pressure': [], 'wind': []}

    response = s3.list_objects_v2(Bucket=DATA_BUCKET, Prefix=prefix)
    for obj in response.get('Contents', []):
        key = obj['Key']
        filename = key.split('/')[-1]

        if filename.startswith('track_') and filename.endswith('.csv'):
            files['gps'].append(key)
        elif filename.startswith('imu_') and filename.endswith('.csv'):
            files['imu'].append(key)
        elif filename.startswith('pressure_') and filename.endswith('.csv'):
            files['pressure'].append(key)
        elif filename.startswith('wind_') and filename.endswith('.csv'):
            files['wind'].append(key)

    return files


def parse_all_gps(s3, keys: list) -> list:
    """Parse all GPS files and return sorted list of (datetime, record) tuples."""
    TIME_CORRECTION_SECONDS = -2460
    all_records = []

    for key in keys:
        print(f"  Reading: {key.split('/')[-1]}")
        try:
            response = s3.get_object(Bucket=DATA_BUCKET, Key=key)
            csv_content = response['Body'].read().decode('utf-8', errors='ignore')
            csv_content = csv_content.replace('\x00', '')

            reader = csv.DictReader(StringIO(csv_content))
            for row in reader:
                ts = row.get('utc_time', '')
                if not ts:
                    continue

                try:
                    dt = datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')
                    dt_corrected = dt + timedelta(seconds=TIME_CORRECTION_SECONDS)

                    if len(ts) > 19 and '.' in ts:
                        millis = ts[20:23] if len(ts) > 22 else ts[20:]
                        full_ts = dt_corrected.strftime('%Y-%m-%dT%H:%M:%S') + '.' + millis + 'Z'
                    else:
                        full_ts = dt_corrected.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

                    record = {
                        't': full_ts,
                        'lat': float(row.get('latitude', 0) or 0),
                        'lon': float(row.get('longitude', 0) or 0),
                        'speed_kn': round(float(row.get('speed_knots', 0) or 0), 2),
                        'course': round(float(row.get('course_deg', 0) or 0), 1),
                        'fix': int(row.get('fix_quality', 0) or 0),
                        'sats': int(row.get('satellites', 0) or 0),
                        'hdop': round(float(row.get('hdop', 99) or 99), 1)
                    }
                    all_records.append((dt_corrected, record))
                except ValueError:
                    continue
        except Exception as e:
            print(f"    Warning: Error reading {key}: {e}")

    # Sort by datetime
    all_records.sort(key=lambda x: x[0])
    return all_records


def split_into_sessions(records: list, gap_minutes: int = 10) -> list:
    """Split records into sessions based on time gaps.

    Returns list of sessions, each session is a list of records.
    """
    if not records:
        return []

    sessions = []
    current_session = [records[0]]

    for i in range(1, len(records)):
        prev_dt = records[i-1][0]
        curr_dt = records[i][0]
        gap = (curr_dt - prev_dt).total_seconds() / 60

        if gap > gap_minutes:
            # Start new session
            sessions.append(current_session)
            current_session = [records[i]]
            print(f"  Session break: {gap:.1f} min gap at {curr_dt.strftime('%H:%M:%S')}")
        else:
            current_session.append(records[i])

    # Don't forget last session
    if current_session:
        sessions.append(current_session)

    return sessions


def downsample_to_1hz(records: list) -> list:
    """Downsample to 1Hz, keeping max speed per second."""
    by_second = defaultdict(list)

    for dt, record in records:
        second = dt.strftime('%Y-%m-%dT%H:%M:%S')
        by_second[second].append(record)

    result = []
    for second, samples in sorted(by_second.items()):
        best = max(samples, key=lambda r: r['speed_kn'])
        best_copy = best.copy()
        best_copy['t'] = second + 'Z'
        result.append(best_copy)

    return result


def parse_sensor_data(s3, keys: list, sensor_type: str, session_bounds: list) -> dict:
    """Parse sensor data and assign to sessions based on time bounds.

    Returns dict mapping session_idx -> list of records.
    """
    TIME_CORRECTION_SECONDS = -2460
    all_records = []

    for key in keys:
        try:
            response = s3.get_object(Bucket=DATA_BUCKET, Key=key)
            csv_content = response['Body'].read().decode('utf-8', errors='ignore')
            csv_content = csv_content.replace('\x00', '')

            reader = csv.DictReader(StringIO(csv_content))
            for row in reader:
                ts = row.get('utc_time', '')
                if not ts:
                    continue

                try:
                    dt = datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')
                    dt_corrected = dt + timedelta(seconds=TIME_CORRECTION_SECONDS)
                    corrected_ts = dt_corrected.strftime('%Y-%m-%dT%H:%M:%SZ')

                    if sensor_type == 'imu':
                        record = parse_imu_row(row, corrected_ts)
                    elif sensor_type == 'pressure':
                        record = parse_pressure_row(row, corrected_ts)
                    elif sensor_type == 'wind':
                        record = parse_wind_row(row, corrected_ts)
                    else:
                        continue

                    all_records.append((dt_corrected, record))
                except ValueError:
                    continue
        except Exception as e:
            print(f"    Warning: Error reading {key}: {e}")

    # Assign records to sessions
    session_data = {i: [] for i in range(len(session_bounds))}

    for dt, record in all_records:
        for i, (start, end) in enumerate(session_bounds):
            # Allow some buffer (1 minute before/after)
            buffer = timedelta(minutes=1)
            if start - buffer <= dt <= end + buffer:
                session_data[i].append(record)
                break

    # Sort and dedupe each session
    for i in session_data:
        seen = set()
        unique = []
        for r in sorted(session_data[i], key=lambda x: x['t']):
            if r['t'] not in seen:
                seen.add(r['t'])
                unique.append(r)
        session_data[i] = unique

    return session_data


def parse_imu_row(row, ts):
    """Parse a single IMU row."""
    # Get averages from row data (single sample)
    raw_heading = float(row.get('heading_deg', 0) or 0)
    corrected_heading = (raw_heading + 180) % 360
    raw_heel = float(row.get('heel_deg', 0) or 0)
    corrected_heel = raw_heel + 90

    return {
        't': ts,
        'heel': round(corrected_heel, 1),
        'pitch': round(float(row.get('pitch_deg', 0) or 0), 1),
        'heading': round(corrected_heading, 1),
        'accel_x': round(float(row.get('accel_x_mps2', 0) or 0), 2),
        'accel_y': round(float(row.get('accel_y_mps2', 0) or 0), 2),
        'accel_z': round(float(row.get('accel_z_mps2', 0) or 0), 2)
    }


def parse_pressure_row(row, ts):
    """Parse a single pressure row."""
    return {
        't': ts,
        'hpa': round(float(row.get('pressure_hpa', 0) or 0), 1),
        'temp_c': round(float(row.get('temperature_c', 0) or 0), 1),
        'trend': row.get('pressure_trend', '')
    }


def parse_wind_row(row, ts):
    """Parse a single wind row."""
    return {
        't': ts,
        'aws_kn': round(float(row.get('apparent_wind_speed_knots', 0) or 0), 1),
        'awa': round(float(row.get('apparent_wind_angle_deg', 0) or 0), 0),
        'heading': round((float(row.get('compass_heading_deg', 0) or 0) + 180) % 360, 1)
    }


def create_manifest(device_id: str, date: str, session_id: str, sensor_data: dict) -> dict:
    """Create session manifest from sensor data."""
    manifest = {
        'device_id': device_id,
        'date': date,
        'session_id': session_id,
        'sensors': {},
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat()
    }

    all_times = []

    for sensor_type, data in sensor_data.items():
        if not data:
            continue

        times = [d['t'] for d in data if 't' in d]
        if not times:
            continue

        manifest['sensors'][sensor_type] = {
            'samples': len(data),
            'start_time': min(times),
            'end_time': max(times)
        }
        all_times.extend(times)

    if all_times:
        manifest['start_time'] = min(all_times)
        manifest['end_time'] = max(all_times)

        try:
            start = datetime.fromisoformat(manifest['start_time'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(manifest['end_time'].replace('Z', '+00:00'))
            manifest['duration_sec'] = int((end - start).total_seconds())
        except:
            pass

    gps_data = sensor_data.get('gps', [])
    if gps_data:
        lats = [d['lat'] for d in gps_data if d.get('lat')]
        lons = [d['lon'] for d in gps_data if d.get('lon')]
        if lats and lons:
            manifest['track_bounds'] = {
                'north': max(lats),
                'south': min(lats),
                'east': max(lons),
                'west': min(lons)
            }

    return manifest


def main():
    parser = argparse.ArgumentParser(description='Restore S1 sessions from raw data')
    parser.add_argument('--profile', default='sailframes', help='AWS profile name')
    parser.add_argument('--dry-run', action='store_true', help='Print what would be done')
    parser.add_argument('--device', default='sailframes-01', help='Device ID')
    parser.add_argument('--date', default='2026-03-24', help='Date to process')
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name='us-east-1')
    s3 = session.client('s3')

    print(f"Processing {args.device}/{args.date}...")

    # List raw files
    files = list_raw_files(s3, args.device, args.date)
    print(f"Found: {len(files['gps'])} GPS, {len(files['imu'])} IMU, "
          f"{len(files['pressure'])} Pressure, {len(files['wind'])} Wind")

    # Parse all GPS data
    print("\nParsing GPS data...")
    all_gps = parse_all_gps(s3, sorted(files['gps']))
    print(f"  Total GPS records: {len(all_gps)}")

    # Split into sessions based on time gaps
    print(f"\nSplitting into sessions (>{SESSION_GAP_MINUTES} min gap)...")
    gps_sessions = split_into_sessions(all_gps, SESSION_GAP_MINUTES)
    print(f"  Found {len(gps_sessions)} sessions")

    # Get session time bounds
    session_bounds = []
    for i, session in enumerate(gps_sessions):
        start_dt = session[0][0]
        end_dt = session[-1][0]
        duration_min = (end_dt - start_dt).total_seconds() / 60
        print(f"  Session {i+1}: {start_dt.strftime('%H:%M:%S')} - {end_dt.strftime('%H:%M:%S')} ({duration_min:.1f} min, {len(session)} points)")
        session_bounds.append((start_dt, end_dt))

    if args.dry_run:
        print("\n[DRY RUN] Would create these sessions:")
        for i, (start, end) in enumerate(session_bounds):
            session_id = start.strftime('%H%M%S')
            print(f"  {args.device}/{args.date}-{session_id}")
        return

    # Parse other sensor data and assign to sessions
    print("\nParsing IMU data...")
    imu_by_session = parse_sensor_data(s3, sorted(files['imu']), 'imu', session_bounds)

    print("Parsing Pressure data...")
    pressure_by_session = parse_sensor_data(s3, sorted(files['pressure']), 'pressure', session_bounds)

    print("Parsing Wind data...")
    wind_by_session = parse_sensor_data(s3, sorted(files['wind']), 'wind', session_bounds)

    # Delete old single session
    old_prefix = f"processed/{args.device}/{args.date}/"
    print(f"\nDeleting old session at {old_prefix}...")
    try:
        response = s3.list_objects_v2(Bucket=DATA_BUCKET, Prefix=old_prefix)
        for obj in response.get('Contents', []):
            s3.delete_object(Bucket=DATA_BUCKET, Key=obj['Key'])
            print(f"  Deleted: {obj['Key']}")
    except Exception as e:
        print(f"  Warning: {e}")

    # Upload each session
    print("\nUploading sessions...")
    for i, gps_session in enumerate(gps_sessions):
        start_dt = gps_session[0][0]
        session_id = start_dt.strftime('%H%M%S')
        folder = f"{args.date}-{session_id}"
        output_prefix = f"processed/{args.device}/{folder}"

        print(f"\n  Session {i+1}: {folder}")

        # Prepare sensor data
        gps_1hz = downsample_to_1hz(gps_session)
        gps_10hz = [r for _, r in gps_session]

        sensor_data = {
            'gps': gps_1hz,
            'imu': imu_by_session.get(i, []),
            'pressure': pressure_by_session.get(i, []),
            'wind': wind_by_session.get(i, [])
        }

        # Upload sensor JSON files
        for sensor_type, data in sensor_data.items():
            if not data:
                continue
            key = f"{output_prefix}/{sensor_type}.json"
            s3.put_object(
                Bucket=DATA_BUCKET,
                Key=key,
                Body=json.dumps(data),
                ContentType='application/json'
            )
            print(f"    {sensor_type}.json: {len(data)} records")

        # Upload 10Hz GPS
        key = f"{output_prefix}/gps_10hz.json"
        s3.put_object(
            Bucket=DATA_BUCKET,
            Key=key,
            Body=json.dumps(gps_10hz),
            ContentType='application/json'
        )
        print(f"    gps_10hz.json: {len(gps_10hz)} records")

        # Create and upload manifest
        manifest = create_manifest(args.device, args.date, session_id, sensor_data)
        manifest_key = f"{output_prefix}/manifest.json"
        s3.put_object(
            Bucket=DATA_BUCKET,
            Key=manifest_key,
            Body=json.dumps(manifest, indent=2),
            ContentType='application/json'
        )
        print(f"    manifest.json (duration: {manifest.get('duration_sec', 0) // 60} min)")

    print(f"\nDone! Created {len(gps_sessions)} sessions")


if __name__ == '__main__':
    main()
