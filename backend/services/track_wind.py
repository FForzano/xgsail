"""Track wind observations: wind directions the analysis worker reads off a
session's own tacks/gybes, stored per session and shared with *other*
sessions sailed nearby at the same time (``wind_lookup.gather_raw_wind``).

Stored per session and replaced wholesale on every analysis upsert — never
folded into the ``wind_estimates`` grid, whose merge double-counts a
re-processed session.
"""

import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..db.models.wind import TRACK_WIND_KINDS
from ..repositories import get_repos
from . import wind_auto_refresh

logger = logging.getLogger(__name__)


def _parse_row(r: dict) -> Optional[dict]:
    """One worker row → a storable dict, or ``None`` if it is malformed."""
    try:
        observed_at = r["observed_at"]
        if isinstance(observed_at, str):
            observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if not isinstance(observed_at, datetime):
            return None
        observed_at = (observed_at.replace(tzinfo=timezone.utc) if observed_at.tzinfo is None
                       else observed_at.astimezone(timezone.utc))
        lat, lng = float(r["lat"]), float(r["lng"])
        twd, confidence = float(r["twd_deg"]), float(r["confidence"])
        kind = r["kind"]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (lat, lng, twd, confidence)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180 and 0 < confidence <= 1):
        return None
    if kind not in TRACK_WIND_KINDS:
        return None
    return {"observed_at": observed_at, "lat": lat, "lng": lng,
            "twd_deg": twd % 360, "confidence": confidence, "kind": kind}


def _parse_rows(session_id: uuid.UUID, raw_rows: list) -> "list[dict]":
    rows = []
    for r in raw_rows:
        parsed = _parse_row(r) if isinstance(r, dict) else None
        if parsed is None:
            logger.warning("track wind observation dropped for session %s: %r", session_id, r)
            continue
        rows.append(parsed)
    return rows


def replace_for_session(session_id: uuid.UUID, raw_rows: list) -> int:
    """Make ``raw_rows`` (the worker's ``track_wind_observations``) the
    session's complete set — ``[]`` clears it. A malformed row is dropped and
    logged rather than failing the rest. Returns the number stored."""
    return get_repos().wind.replace_track_observations(
        session_id, _parse_rows(session_id, raw_rows))


# Two observations of one session across re-analyses are "the same" when they
# are of the same kind and read off (nearly) the same instant; the worker
# derives observed_at from the maneuver's timing, which a re-run does not move
# by more than a sample or two.
MATCH_TOLERANCE = timedelta(seconds=5)
# Below this a matched observation's direction change is noise, not news worth
# re-analysing neighbours for.
TWD_CHANGE_DEG = 3.0


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def changed_observations(previous: list, current: "list[dict]") -> "list[dict]":
    """What a neighbour would see differently: observations added, removed,
    or matched (same kind, ``observed_at`` within ``MATCH_TOLERANCE``) but
    with the direction moved by more than ``TWD_CHANGE_DEG``. ``previous``
    rows may be ORM objects or dicts; each returned item carries
    ``observed_at``/``lat``/``lng`` — all the neighbour search needs."""
    def as_dict(o):
        if isinstance(o, dict):
            return {**o, "observed_at": _aware(o["observed_at"])}
        return {"observed_at": _aware(o.observed_at), "lat": o.lat, "lng": o.lng,
                "twd_deg": o.twd_deg, "kind": o.kind}

    unmatched_old = [as_dict(o) for o in previous]
    changed = []
    for new in (as_dict(o) for o in current):
        best, best_dt = None, None
        for i, old in enumerate(unmatched_old):
            dt = abs(old["observed_at"] - new["observed_at"])
            if old["kind"] == new["kind"] and dt <= MATCH_TOLERANCE and (
                    best_dt is None or dt < best_dt):
                best, best_dt = i, dt
        if best is None:
            changed.append(new)
            continue
        old = unmatched_old.pop(best)
        delta = abs((new["twd_deg"] - old["twd_deg"] + 180) % 360 - 180)
        if delta > TWD_CHANGE_DEG:
            changed.append(new)
    return changed + unmatched_old


PAYLOAD_KEY = "track_wind_observations"


def apply_analysis_payload(session_id: uuid.UUID, payload: dict, *,
                           mark_neighbours: bool = False) -> Optional[int]:
    """Store the observations carried by a worker's analysis payload.

    Key absent → an older worker image that knows nothing of them: the stored
    set is left alone (returns ``None``). Key present, even ``[]`` → the
    complete new set. Best-effort, like ``_apply_wind_refinements`` in
    ``routers/system.py``: a failure only costs neighbouring sessions a
    refinement, never the analysis upsert that carried it.

    ``mark_neighbours``: when the new set differs materially from the stored
    one (``changed_observations``), flag the sessions nearby for a wind
    refresh — see ``services/wind_auto_refresh.py``. The caller passes
    ``False`` for an analysis that was itself an automatic refresh."""
    if PAYLOAD_KEY not in payload:
        return None
    repos = get_repos()
    try:
        observations = payload[PAYLOAD_KEY]
        if not isinstance(observations, list):
            raise TypeError(f"expected a list, got {type(observations).__name__}")
        rows = _parse_rows(session_id, observations)
        previous = repos.wind.list_track_observations(session_id) if mark_neighbours else []
        stored = repos.wind.replace_track_observations(session_id, rows)
    except Exception:
        logger.warning("track wind observations not stored for session %s", session_id,
                       exc_info=True)
        return None
    if mark_neighbours:
        try:
            changed = changed_observations(previous, rows)
            if changed:
                wind_auto_refresh.mark_neighbours(session_id, changed)
        except Exception:
            logger.warning("neighbour wind marking failed for session %s", session_id,
                           exc_info=True)
    return stored
