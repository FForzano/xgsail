#!/usr/bin/env python3
"""Create the missing tracking activity for races scheduled before the
start-list feature landed.

A race's activity used to be created lazily, on the first management action
after the race. That is too late for the recording screen, which offers a
sailor the races they are entered for *before* the start — a race with no
activity yet is invisible there. New races now get their activity at creation
(``routers/races.py::create_race``); this backfills the ones already in the
database.

Only upcoming races are touched: a past race without an activity never had
tracked sessions, and inventing one would add empty entries to the diary.

Run it with the backend environment configured (DB), e.g. in the backend
container:

    python scripts/backfill_race_activities.py            # dry run
    python scripts/backfill_race_activities.py --apply
"""

import argparse
from datetime import datetime, timezone

from backend.repositories import get_repos
from backend.routers.races import _create_race_activity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually create the activities (default: dry run)")
    args = parser.parse_args()

    repos = get_repos()
    now = datetime.now(timezone.utc)
    created = 0

    for regatta in repos.regattas.list():
        for raceday in repos.racedays.list(regatta_id=regatta.id):
            for race in repos.races.list(race_day_id=raceday.id):
                if repos.activities.get_by_race(race.id) is not None:
                    continue
                # start_time is optional; fall back to the race day's date so a
                # race scheduled without a time is still covered.
                when = race.start_time or datetime.combine(
                    raceday.date, datetime.min.time(), tzinfo=timezone.utc
                )
                if when < now:
                    continue
                label = f"{regatta.name} — race {race.race_number} ({when:%Y-%m-%d %H:%M})"
                if args.apply:
                    _create_race_activity(race)
                    print(f"created activity for {label}")
                else:
                    print(f"would create activity for {label}")
                created += 1

    verb = "Created" if args.apply else "Would create"
    print(f"\n{verb} {created} activit{'y' if created == 1 else 'ies'}.")
    if created and not args.apply:
        print("Re-run with --apply to write.")


if __name__ == "__main__":
    main()
