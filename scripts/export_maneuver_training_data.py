#!/usr/bin/env python3
"""Export session_maneuvers rows into a flat CSV for the maneuver-classifier
training worker (workers/train_maneuver/).

Flattens each row's ``features`` JSON (workers/process_upload/processing/
maneuver_features.py) into its own columns, plus ``session_id`` (needed for
the group-aware train/val/test split — maneuvers from the same session are
correlated and must not leak across splits) and the label/provenance columns
below.

``label`` = the row's current ``maneuver_type`` — this IS ground truth for
any row a user has corrected via ``PATCH /sessions/{id}/maneuvers/{id}``
(routers/sessions.py::correct_maneuver), and the algorithm's raw guess
otherwise. The one exception: a row the user rejected as "not a real
maneuver" (``PATCH .../maneuvers/{id}/reject``) exports as ``false_alarm``
regardless of ``maneuver_type`` — that's the real negative-example signal
the training worker's classes always anticipated but, until rejection
existed in the app, never actually had. ``label_original`` =
``original_maneuver_type``, frozen at whatever the pipeline first assigned
and never touched by a correction or rejection; a row where
``label != label_original`` was touched by a human. ``source``
(``detected``/``manual``) and ``rejected`` mirror the DB's own columns, kept
alongside for filtering without recomputing anything.

You can still hand-edit ``label`` further in a spreadsheet before training —
just don't touch ``label_original``/``source``/``rejected``, they're read
from the DB as-is. The trainer reports the corrected-vs-algorithm-only split
before every run (see train.py) as a quick data-quality signal.

Rows with a mismatched feature schema version are still exported but flagged
via ``schema_version`` so you can decide whether to include them.

Read-only — it only queries, never writes. Run it with the backend
environment configured (DB reachable), e.g. inside the backend container:

    python scripts/export_maneuver_training_data.py --out maneuvers.csv
"""

import argparse
import csv
import sys

from backend.db import get_sessionmaker
from backend.db.models.session import SessionManeuverORM
from workers.process_upload.processing.maneuver_features import (
    CORE_FEATURES,
    ENABLED_FEATURES,
)

# Fixed column order for the feature part of the CSV — same list the
# training worker will use to build its feature matrix, so the two stay in
# lockstep without duplicating the list by hand.
FEATURE_COLUMNS = list(dict.fromkeys(CORE_FEATURES + tuple(ENABLED_FEATURES)))

META_COLUMNS = ["maneuver_id", "session_id", "label", "label_original",
               "corrected_by_user", "source", "rejected", "schema_version"]

FALSE_ALARM_LABEL = "false_alarm"


def export(out_path: str) -> int:
    Session = get_sessionmaker()
    with Session() as db:
        rows = (
            db.query(SessionManeuverORM)
            .filter(SessionManeuverORM.features.isnot(None))
            .order_by(SessionManeuverORM.session_id)
            .all()
        )

        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=META_COLUMNS + FEATURE_COLUMNS)
            writer.writeheader()
            for row in rows:
                features = row.features or {}
                out_row = {
                    "maneuver_id": str(row.id),
                    "session_id": str(row.session_id),
                    "label": FALSE_ALARM_LABEL if row.rejected else row.maneuver_type,
                    "label_original": row.original_maneuver_type,
                    "corrected_by_user": row.corrected_by_user,
                    "source": row.source,
                    "rejected": row.rejected,
                    "schema_version": features.get("_schema_version"),
                }
                for col in FEATURE_COLUMNS:
                    out_row[col] = features.get(col)
                writer.writerow(out_row)

        return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="maneuver_training_data.csv", help="Output CSV path")
    args = parser.parse_args()

    count = export(args.out)
    print(f"Wrote {count} maneuvers to {args.out}", file=sys.stderr)
    if count == 0:
        print("No maneuvers with a persisted feature vector yet — nothing to train on.", file=sys.stderr)


if __name__ == "__main__":
    main()
