"""Time-window reconciliation between a fresh worker analysis and a
session's already-persisted, user-touched maneuvers.

Pure functions, no DB access — ``repositories/sql/session_repo.py::
upsert_maneuvers`` calls this to decide which freshly-detected candidates
to actually insert, then does the DB mutations itself.

Every reanalysis produces a brand new candidate list from scratch (the
worker is DB-blind and knows nothing about prior corrections). Without
reconciliation this would blow away any user correction/rejection/manual
addition on every run — see the "known limitation" this module replaces in
``upsert_maneuvers``'s prior docstring. The rule: any row a user has
touched (manually added, retyped, or rejected) is "preserved" — it's never
deleted, and any fresh candidate that turns out to describe the same
real-world event is dropped instead of inserted alongside it, so the
session never accumulates duplicates.
"""

# Must stay strictly below MIN_MANEUVER_SPACING_SEC (20s, in
# workers/process_upload/processing/maneuvers.py) — that constant is the
# detector's own floor for "two maneuvers are far enough apart to be
# distinct". A match tolerance at or above it could conflate two genuinely
# separate, closely-spaced real maneuvers into one. A maneuver's own
# duration is well under MAX_MANEUVER_DURATION_SEC (30s), so 15s of padding
# on each side comfortably covers boundary-refinement jitter between two
# independent computations of "the same" turn.
OVERLAP_TOLERANCE_SEC = 15.0


def _same_event(candidate: dict, preserved: dict) -> bool:
    """Do these two maneuvers' time windows describe the same real-world
    event? Padded-interval overlap, not exact/point matching — two
    independent boundary computations (the algorithm's vs. a user's click,
    or the algorithm's this run vs. last run) rarely agree to the second."""
    c_start = candidate["start_time"] - OVERLAP_TOLERANCE_SEC
    c_end = candidate["end_time"] + OVERLAP_TOLERANCE_SEC
    p_start = preserved["start_time"] - OVERLAP_TOLERANCE_SEC
    p_end = preserved["end_time"] + OVERLAP_TOLERANCE_SEC
    return c_start <= p_end and p_start <= c_end


def reconcile(preserved: "list[dict]", candidates: "list[dict]") -> "list[dict]":
    """Returns the subset of ``candidates`` (fresh worker output, no id) that
    should actually be inserted: any candidate whose time window overlaps a
    ``preserved`` row (an existing DB row the user has manually added,
    corrected, or rejected — dicts need at least ``start_time``/
    ``end_time``) is dropped, since that preserved row already represents
    this event and user data always wins. ``preserved`` itself is never
    mutated or returned — the caller keeps those rows exactly as they are.
    """
    return [
        c for c in candidates
        if not any(_same_event(c, p) for p in preserved)
    ]
