#!/usr/bin/env python3
"""One-shot, idempotent backfill: historical sessions -> ``visibility=public``.

Phase 5 makes **new** sessions ``private`` by default. The public dashboard
(``race.html`` / ``sessions.html``) reads anonymously, so pre-existing sessions
must be flipped to ``public`` once, or they would vanish from the anonymous
views. This script does exactly that — it sets ``visibility=public`` on every
session that does not already carry an explicit non-private visibility.

Design notes (per docs/user_plan.md / user_plan_next_phases.md):
- **Backend-agnostic.** Runs through ``get_repos()`` (object blob JSON or
  Postgres) and writes via ``SessionRepo.upsert`` — the authoritative store of
  the deploy. Pick the backend with ``SAILFRAMES_METADATA_BACKEND``.
- **Idempotent.** Re-running only touches sessions still at the default
  ``private`` with no owner/crew, so an already-public (or user-claimed private)
  session is never rewritten.
- On Postgres, run ``SqlSessionRepo.bootstrap_from_blob()`` first (or ensure the
  table is populated) so historical manifests exist as rows before the flip.

Usage:
    SAILFRAMES_METADATA_BACKEND=object   python scripts/backfill_session_visibility.py [--dry-run]
    SAILFRAMES_METADATA_BACKEND=postgres python scripts/backfill_session_visibility.py [--dry-run]
"""

import argparse
import pathlib
import sys

# web/ on sys.path so ``import api...`` works regardless of CWD.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "web"))


def backfill(dry_run: bool = False) -> None:
    from api.repositories import get_repos, select_metadata_backend

    repos = get_repos()
    print(f"Backend: {select_metadata_backend()}")

    # On Postgres, make sure historical manifests are present as rows first.
    boot = getattr(repos.sessions, "bootstrap_from_blob", None)
    if callable(boot) and not dry_run:
        imported = boot()
        if imported:
            print(f"  bootstrapped {imported} manifest(s) into the DB")

    flipped = skipped = 0
    for s in repos.sessions.list():
        # Only touch sessions still at the untouched default: private, no owner,
        # no crew. A user who deliberately kept a session private is left alone.
        already_set = s.visibility != "private" or s.owner_user_id is not None or (s.crew or [])
        if already_set:
            skipped += 1
            continue
        if dry_run:
            print(f"  [would flip] {s.device_id}/{s.date} -> public")
            flipped += 1
            continue
        s.visibility = "public"
        repos.sessions.upsert(s)
        flipped += 1
        print(f"  [flipped] {s.device_id}/{s.date} -> public")

    verb = "would flip" if dry_run else "flipped"
    print(f"\nDone. {verb}={flipped} left-untouched={skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
