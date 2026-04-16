#!/usr/bin/env python3
"""
Restore S1 (sailframes-01) sessions by processing raw CSV files locally.

The S1 files use flat structure with prefix naming (track_, imu_, pressure_, wind_)
which differs from E1's suffix naming (_nav.csv, _imu.csv, etc.).

Usage:
    python scripts/restore_s1_session.py
    python scripts/restore_s1_session.py --dry-run
"""

import argparse
import boto3
import csv
import json
from io import StringIO
from datetime import datetime, timezone, timedelta
from collections import defaultdict

DATA_BUCKET = 'sailframes-fleet-data-prod'


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


def process_gps(s3, keys: list) -> tuple:
    """Process GPS track files, return (data_1hz, data_10hz)."""
    # Time correction for S1 (Pi5 clock was ~41 minutes ahead)
    TIME_CORRECTION_SECONDS = -2460

    all_10hz = []
    by_second = defaultdict(list)

    for key in keys:
        print(f"  Processing: {key.split('/')[-1]}")
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
                    second = dt_corrected.strftime('%Y-%m-%dT%H:%M:%S')

                    if len(ts) > 19 and '.' in ts:
                        millis = ts[20:23] if len(ts) > 22 else ts[20:]
                        full_ts = dt_corrected.strftime('%Y-%m-%dT%H:%M:%S') + '.' + millis + 'Z'
                    else:
                        full_ts = second + 'Z'
                except ValueError:
                    continue

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
                all_10hz.append(record)
                by_second[second].append(row)
        except Exception as e:
            print(f"    Warning: Error processing {key}: {e}")

    # Sort 10Hz
    all_10hz.sort(key=lambda x: x['t'])

    # Downsample to 1Hz (take max speed per second)
    result_1hz = []
    for second, samples in sorted(by_second.items()):
        best = max(samples, key=lambda r: float(r.get('speed_knots', 0) or 0))
        result_1hz.append({
            't': second + 'Z',
            'lat': float(best.get('latitude', 0) or 0),
            'lon': float(best.get('longitude', 0) or 0),
            'speed_kn': round(float(best.get('speed_knots', 0) or 0), 2),
            'course': round(float(best.get('course_deg', 0) or 0), 1),
            'fix': int(best.get('fix_quality', 0) or 0),
            'sats': int(best.get('satellites', 0) or 0),
            'hdop': round(float(best.get('hdop', 99) or 99), 1)
        })

    return result_1hz, all_10hz


def process_imu(s3, keys: list) -> list:
    """Process IMU files."""
    TIME_CORRECTION_SECONDS = -2460
    by_second = defaultdict(list)

    for key in keys:
        print(f"  Processing: {key.split('/')[-1]}")
        try:
            response = s3.get_object(Bucket=DATA_BUCKET, Key=key)
            csv_content = response['Body'].read().decode('utf-8', errors='ignore')
            # Remove NUL bytes that can corrupt CSV parsing
            csv_content = csv_content.replace('\x00', '')

            reader = csv.DictReader(StringIO(csv_content))
            for row in reader:
                ts = row.get('utc_time', '')
                if not ts:
                    continue
                try:
                    dt = datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')
                    dt_corrected = dt + timedelta(seconds=TIME_CORRECTION_SECONDS)
                    second = dt_corrected.strftime('%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    continue
                by_second[second].append(row)
        except Exception as e:
            print(f"    Warning: Error processing {key}: {e}")

    result = []
    for second, samples in sorted(by_second.items()):
        n = len(samples)
        avg = lambda field: sum(float(r.get(field, 0) or 0) for r in samples) / n

        # IMU mounted 180° (X-axis toward stern)
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


def process_pressure(s3, keys: list) -> list:
    """Process pressure files."""
    TIME_CORRECTION_SECONDS = -2460
    result = []

    for key in keys:
        print(f"  Processing: {key.split('/')[-1]}")
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
                except ValueError:
                    continue

                result.append({
                    't': corrected_ts,
                    'hpa': round(float(row.get('pressure_hpa', 0) or 0), 1),
                    'temp_c': round(float(row.get('temperature_c', 0) or 0), 1),
                    'trend': row.get('pressure_trend', '')
                })
        except Exception as e:
            print(f"    Warning: Error processing {key}: {e}")

    return result


def process_wind(s3, keys: list) -> list:
    """Process wind files."""
    TIME_CORRECTION_SECONDS = -2460
    result = []

    for key in keys:
        print(f"  Processing: {key.split('/')[-1]}")
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
                except ValueError:
                    continue

                result.append({
                    't': corrected_ts,
                    'aws_kn': round(float(row.get('apparent_wind_speed_knots', 0) or 0), 1),
                    'awa': round(float(row.get('apparent_wind_angle_deg', 0) or 0), 0),
                    'heading': round((float(row.get('compass_heading_deg', 0) or 0) + 180) % 360, 1)
                })
        except Exception as e:
            print(f"    Warning: Error processing {key}: {e}")

    return result


def dedupe_sort(records):
    """Remove duplicates and sort by timestamp."""
    seen = set()
    unique = []
    for r in records:
        t = r.get('t', '')
        if t and t not in seen:
            seen.add(t)
            unique.append(r)
    unique.sort(key=lambda x: x['t'])
    return unique


def create_manifest(device_id: str, date: str, sensor_data: dict) -> dict:
    """Create session manifest from sensor data."""
    manifest = {
        'device_id': device_id,
        'date': date,
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

        # Calculate duration
        try:
            start = datetime.fromisoformat(manifest['start_time'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(manifest['end_time'].replace('Z', '+00:00'))
            manifest['duration_sec'] = int((end - start).total_seconds())
        except:
            pass

    # Calculate track bounds from GPS
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

    if args.dry_run:
        print("[DRY RUN] Would process files and upload to S3")
        return

    # Process each sensor type
    sensor_data = {}

    if files['gps']:
        print("\nProcessing GPS...")
        gps_1hz, gps_10hz = process_gps(s3, sorted(files['gps']))
        gps_1hz = dedupe_sort(gps_1hz)
        gps_10hz = dedupe_sort(gps_10hz)
        sensor_data['gps'] = gps_1hz
        print(f"  -> {len(gps_1hz)} 1Hz, {len(gps_10hz)} 10Hz records")

    if files['imu']:
        print("\nProcessing IMU...")
        imu_data = process_imu(s3, sorted(files['imu']))
        imu_data = dedupe_sort(imu_data)
        sensor_data['imu'] = imu_data
        print(f"  -> {len(imu_data)} records")

    if files['pressure']:
        print("\nProcessing Pressure...")
        pressure_data = process_pressure(s3, sorted(files['pressure']))
        pressure_data = dedupe_sort(pressure_data)
        sensor_data['pressure'] = pressure_data
        print(f"  -> {len(pressure_data)} records")

    if files['wind']:
        print("\nProcessing Wind...")
        wind_data = process_wind(s3, sorted(files['wind']))
        wind_data = dedupe_sort(wind_data)
        sensor_data['wind'] = wind_data
        print(f"  -> {len(wind_data)} records")

    # Create manifest
    print("\nCreating manifest...")
    manifest = create_manifest(args.device, args.date, sensor_data)

    # Upload to S3
    output_prefix = f"processed/{args.device}/{args.date}"
    print(f"\nUploading to {output_prefix}/...")

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
        print(f"  Uploaded: {sensor_type}.json ({len(data)} records)")

    # Upload 10Hz GPS if we have it
    if files['gps']:
        key = f"{output_prefix}/gps_10hz.json"
        s3.put_object(
            Bucket=DATA_BUCKET,
            Key=key,
            Body=json.dumps(gps_10hz),
            ContentType='application/json'
        )
        print(f"  Uploaded: gps_10hz.json ({len(gps_10hz)} records)")

    # Upload manifest
    manifest_key = f"{output_prefix}/manifest.json"
    s3.put_object(
        Bucket=DATA_BUCKET,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2),
        ContentType='application/json'
    )
    print(f"  Uploaded: manifest.json")

    print(f"\nDone! Session restored: {args.device}/{args.date}")
    print(f"  Duration: {manifest.get('duration_sec', 0) // 60} minutes")
    print(f"  Start: {manifest.get('start_time')}")
    print(f"  End: {manifest.get('end_time')}")


if __name__ == '__main__':
    main()
