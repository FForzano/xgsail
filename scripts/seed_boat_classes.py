#!/usr/bin/env python3
"""Seed/update ``boat_classes`` from three official RYA Portsmouth Yardstick
sources, layered by authority (data/ — all extracted from PDFs/xlsx
published at https://www.rya.org.uk/racing/portsmouth-yardstick):

1. ``rya_py_list_2026.json`` — the current "PN List 2026" (Dinghy + Multi +
   Experimental Numbers sections): classes with a consistent return of
   results this season. Authoritative for everything, including
   ``py_rating``.
2. ``rya_py_limited_data_2026.json`` — the "Limited Data List 2026":
   classes without enough recent returns for the main list. Used only for
   classes NOT already covered by the PN list; its ``py_rating`` is the
   list's own "Last Published Number" (may be old — RYA publishes it as a
   starting point, not a current number). Roughly half its rows have no
   RYA Class ID at all (older/rarer classes never assigned one).
3. ``rya_class_master_2026.json`` — the "Class List Master" (523 class
   configurations, keyed by RYA Class ID): no PY numbers. Used two ways:
   (a) to backfill crew/rig/spinnaker/hull_type when a Limited Data List
   row is missing them and has a matching ID (e.g. "470"/RYA ID 13 has a
   PY number on the Limited Data List but no crew/rig/spinnaker there —
   pulled from the master list instead); (b) every remaining class in the
   master list that has an RYA Class ID but never made either PY list is
   still imported, with ``py_rating`` left ``NULL`` — a class configuration
   is real and worth having in the catalog even with no number yet; an
   admin can fill it in by hand later once one is available.

Only RYA-published fields are ever touched: ``name``, ``rya_class_id``,
``crew_size``, ``rig_type``, ``spinnaker_type``, ``py_rating``, ``hull_type``.
``description``/``logo_id``/``loa_m``/``beam_m``/``sail_area_sqm`` are never
touched — those are admin-filled extras outside the RYA lists' scope, and
this script must not clobber whatever an admin has already entered there.

The one non-RYA field it fills is ``silhouette`` (the replay map's class
drawing), from ``data/class_silhouettes.json`` — and only where it is still
NULL, so an admin's choice always wins.

Idempotent and safe to re-run every time the RYA republishes a list: matches
existing rows by ``rya_class_id`` first, falling back to a case-insensitive
exact ``name`` match for a class created locally (or sourced from the
Limited Data list with no ID) before it had an RYA ID — that class gets
linked, not duplicated. Anything left unmatched is created. If the name
match already carries a *different* RYA Class ID, the row is skipped rather
than silently re-pointing an existing link (happens for a handful of master
rows that share a name with an unrelated already-published class, e.g. two
distinct "Spitfire" configurations — needs a human to disambiguate).

Run with the backend environment configured (DB reachable), e.g. inside the
backend container:

    python scripts/seed_boat_classes.py            # apply
    python scripts/seed_boat_classes.py --dry-run  # preview only
"""

import argparse
import json
import sys
from pathlib import Path

from backend.repositories import get_repos

DATA_DIR = Path(__file__).parent / "data"
PN_FILE = DATA_DIR / "rya_py_list_2026.json"
LIMITED_FILE = DATA_DIR / "rya_py_limited_data_2026.json"
MASTER_FILE = DATA_DIR / "rya_class_master_2026.json"
SILHOUETTES_FILE = DATA_DIR / "class_silhouettes.json"

RYA_FIELDS = ("name", "rya_class_id", "crew_size", "rig_type", "spinnaker_type",
              "py_rating", "hull_type")
STRUCTURAL_FIELDS = ("crew_size", "rig_type", "spinnaker_type", "hull_type")


def _key(row: dict):
    """Merge key: RYA Class ID when known, else a case-insensitive name —
    some Limited Data List rows (older/rarer classes) have no ID at all."""
    return row["rya_class_id"] if row.get("rya_class_id") is not None else \
        ("name", row["name"].strip().lower())


def build_merged_rows() -> list[dict]:
    pn_rows = json.loads(PN_FILE.read_text())
    limited_rows = json.loads(LIMITED_FILE.read_text())
    master_rows = json.loads(MASTER_FILE.read_text())
    master_by_id = {r["rya_class_id"]: r for r in master_rows}

    merged: dict[object, dict] = {}
    for row in pn_rows:
        merged[_key(row)] = {**row}

    for row in limited_rows:
        k = _key(row)
        if k in merged:
            continue  # already have the current, more complete PN List row
        entry = {**row, "hull_type": None}
        master = master_by_id.get(row.get("rya_class_id"))
        if master:
            for field in STRUCTURAL_FIELDS:
                if entry.get(field) is None:
                    entry[field] = master.get(field)
        merged[k] = entry

    # Every remaining master-list class with an RYA Class ID that never made
    # either PY list — imported anyway, py_rating stays NULL.
    for row in master_rows:
        k = row["rya_class_id"]
        if k in merged:
            continue
        merged[k] = {**row, "py_rating": None}

    return list(merged.values())


def silhouette_for(row: dict, silhouettes: dict):
    """The drawing a class gets by default: by RYA Class ID, else by name."""
    by_id = silhouettes["by_rya_class_id"].get(str(row.get("rya_class_id")))
    return by_id or silhouettes["by_name"].get(row["name"].strip().lower())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="preview changes, write nothing")
    args = parser.parse_args()

    rows = build_merged_rows()
    silhouettes = json.loads(SILHOUETTES_FILE.read_text())
    repos = get_repos()
    existing = repos.boats.list_classes(limit=10_000)
    by_rya_id = {c.rya_class_id: c for c in existing if c.rya_class_id is not None}
    by_name = {c.name.strip().lower(): c for c in existing}

    created = updated = unchanged = skipped = 0
    for row in rows:
        match = by_rya_id.get(row["rya_class_id"])
        if match is None:
            name_match = by_name.get(row["name"].strip().lower())
            if name_match is not None:
                if (name_match.rya_class_id is not None
                        and name_match.rya_class_id != row["rya_class_id"]):
                    print(f"SKIP    {row['name']!r} (RYA ID {row['rya_class_id']}) — "
                          f"name already linked to RYA ID {name_match.rya_class_id}, "
                          "needs manual review")
                    skipped += 1
                    continue
                match = name_match
        if match is None:
            print(f"CREATE  {row['name']!r} (RYA ID {row['rya_class_id']})")
            if not args.dry_run:
                repos.boats.create_class({k: row[k] for k in RYA_FIELDS}
                                         | {"silhouette": silhouette_for(row, silhouettes)})
            created += 1
            continue

        changes = {k: row[k] for k in RYA_FIELDS
                   if row[k] is not None and getattr(match, k) != row[k]}
        silhouette = silhouette_for(row, silhouettes)
        if match.silhouette is None and silhouette is not None:
            changes["silhouette"] = silhouette
        if not changes:
            unchanged += 1
            continue
        print(f"UPDATE  {match.name!r} -> {changes}")
        if not args.dry_run:
            repos.boats.update_class(match.id, changes)
        updated += 1

    print(f"\n{created} created, {updated} updated, {unchanged} unchanged, {skipped} skipped"
          f"{' (dry run — nothing written)' if args.dry_run else ''}")


if __name__ == "__main__":
    sys.exit(main())
