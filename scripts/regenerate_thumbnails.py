#!/usr/bin/env python3
"""Re-dispatch thumbnail rendering for existing activities.

``workers/process_upload/thumbnail.py`` was rewritten to composite the track
over an OpenStreetMap raster background (previously a transparent
track-only overlay), at 640x480 instead of 320x240. Nothing re-renders
thumbnails already sitting in storage — they only refresh when a session is
reprocessed or someone hits the per-activity
``POST /api/activities/{id}/regenerate-thumbnail`` endpoint. This script
walks every activity and dispatches that same regeneration in bulk, going
through the backend's own helpers (``activity_thumbnail_prefixes``,
``dispatch_activity_thumbnail``, ``bucket_name``) rather than reimplementing
the worker-dispatch payload here.

Each render fetches up to 9 tiles from the public OpenStreetMap tile server
(``THUMBNAIL_TILE_URL``, see ``thumbnail.py``) — please be polite to it:
keep ``--delay`` at a sane default, and for a large backfill point
``THUMBNAIL_TILE_URL`` at a self-hosted tile server instead of the public
one.

Run it with the backend environment configured (DB + PROCESS_UPLOAD_URL),
e.g. in the backend container:

    python scripts/regenerate_thumbnails.py                  # dry run
    python scripts/regenerate_thumbnails.py --apply
    python scripts/regenerate_thumbnails.py --apply --limit 50 --delay 2
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Run directly (not via `python -m` with the repo root on PYTHONPATH already,
# as `pytest` sets it up) — put the repo root on sys.path so `backend.*`
# resolves the same way it does inside the backend container.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.repositories import get_repos  # noqa: E402
from backend.services import ingestion  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="actually dispatch the regenerations (default: dry run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="explicitly request a dry run (the default when --apply is absent)")
    parser.add_argument("--limit", type=int, default=None,
                        help="only consider the first N activities (default: all)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="seconds to sleep between dispatches, to go easy on the "
                             "tile server (default: 1.0)")
    args = parser.parse_args()

    apply = args.apply and not args.dry_run
    repos = get_repos()
    bucket = ingestion.bucket_name()

    dispatched = 0
    skipped = 0

    activities = repos.activities.list(viewer_is_superadmin=True, limit=args.limit)
    for activity in activities:
        prefixes = ingestion.activity_thumbnail_prefixes(activity.id)
        if not prefixes:
            skipped += 1
            continue
        if apply:
            ingestion.dispatch_activity_thumbnail(bucket, activity.id, prefixes)
            logger.info("dispatched thumbnail regeneration for activity %s", activity.id)
            time.sleep(args.delay)
        else:
            logger.info("would dispatch thumbnail regeneration for activity %s", activity.id)
        dispatched += 1

    verb = "Dispatched" if apply else "Would dispatch"
    print(f"\n{verb} {dispatched} regeneration(s), skipped {skipped} activity(ies) "
          f"with no processed sessions.")
    if dispatched and not apply:
        print("Re-run with --apply to write.")


if __name__ == "__main__":
    main()
