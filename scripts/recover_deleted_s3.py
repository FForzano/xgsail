#!/usr/bin/env python3
"""
Recover deleted S3 objects by removing delete markers.
S3 versioning preserves deleted objects - we just need to remove the delete markers.

Usage:
    python scripts/recover_deleted_s3.py --dry-run
    python scripts/recover_deleted_s3.py
"""

import argparse
import boto3

DATA_BUCKET = 'sailframes-fleet-data-prod'


def list_delete_markers(s3, prefix: str) -> list:
    """List all delete markers under a prefix."""
    markers = []
    paginator = s3.get_paginator('list_object_versions')

    for page in paginator.paginate(Bucket=DATA_BUCKET, Prefix=prefix):
        for marker in page.get('DeleteMarkers', []):
            if marker.get('IsLatest', False):
                markers.append({
                    'Key': marker['Key'],
                    'VersionId': marker['VersionId']
                })

    return markers


def remove_delete_markers(s3, markers: list, dry_run: bool = False) -> int:
    """Remove delete markers to restore objects."""
    restored = 0

    for i, marker in enumerate(markers):
        if dry_run:
            print(f"  [DRY RUN] Would restore: {marker['Key']}")
        else:
            try:
                s3.delete_object(
                    Bucket=DATA_BUCKET,
                    Key=marker['Key'],
                    VersionId=marker['VersionId']
                )
                restored += 1
                if restored % 50 == 0:
                    print(f"  Restored {restored}/{len(markers)} files...")
            except Exception as e:
                print(f"  Error restoring {marker['Key']}: {e}")

    return restored


def main():
    parser = argparse.ArgumentParser(description='Recover deleted S3 objects')
    parser.add_argument('--profile', default='sailframes', help='AWS profile name')
    parser.add_argument('--dry-run', action='store_true', help='Print what would be done')
    parser.add_argument('--prefix', default='', help='Only recover under this prefix')
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name='us-east-1')
    s3 = session.client('s3')

    prefixes_to_recover = [
        'raw/E1/',
        'raw/sailframes-01/',
        'processed/',
    ]

    if args.prefix:
        prefixes_to_recover = [args.prefix]

    total_restored = 0

    for prefix in prefixes_to_recover:
        print(f"\nScanning {prefix}...")
        markers = list_delete_markers(s3, prefix)
        print(f"  Found {len(markers)} deleted objects")

        if markers:
            if args.dry_run:
                # Show sample of what would be restored
                for marker in markers[:10]:
                    print(f"  [DRY RUN] Would restore: {marker['Key']}")
                if len(markers) > 10:
                    print(f"  ... and {len(markers) - 10} more")
            else:
                restored = remove_delete_markers(s3, markers, args.dry_run)
                total_restored += restored
                print(f"  Restored {restored} objects")

    print(f"\n{'='*50}")
    if args.dry_run:
        print(f"DRY RUN complete. Would restore files from {len(prefixes_to_recover)} prefixes.")
    else:
        print(f"Recovery complete! Restored {total_restored} total objects.")


if __name__ == '__main__':
    main()
