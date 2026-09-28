"""Neighbour-driven wind re-analysis.

A session with no onboard wind sensor has its wind direction corrected by the
tack/gybe observations of boats sailing nearby (``services/track_wind.py``,
``wind_lookup.gather_raw_wind``) — but only those already on file when its
``wind_cache.json`` was written. Boat A analysed at 17:00 never benefits from
boat B, same water and time, uploaded at 20:00. This module closes that gap
without letting it turn into a compute or Open-Meteo storm:

- **Mark only on material change.** ``track_wind.apply_analysis_payload``
  diffs a session's new observation set against the stored one and calls
  ``mark_neighbours`` only for what changed; marking stamps
  ``sessions.wind_stale_at``, it never dispatches.
- **One generation.** ``run_pending`` sets ``wind_auto_refresh_pending_at``
  right before dispatching; the analysis upsert consumes it
  (``consume_auto_flag``) and then marks nobody, so A's refresh caused by B
  never refreshes C, D, ... in turn.
- **Coalesced and rate-limited.** The processor, kicked by the scheduler,
  takes sessions stale for at least ``AUTO_REFRESH_DEBOUNCE`` (a regatta's
  boats upload over an evening: one refresh per boat, not per upload), at
  most ``AUTO_REFRESH_MAX_PER_RUN`` per run, none attempted within
  ``AUTO_REFRESH_COOLDOWN``.
- **Single flight, sequential.** One run per process (``_run_gate``, taken
  non-blocking like ``osm_poi._query_gate``: a second trigger is a no-op), and
  refreshes one after another — the local Lambda RIE worker crashes on
  overlapping invocations (see ``routers/system.py::
  _regenerate_activity_thumbnail``).

Proximity comes from the neighbours' own ``session_legs`` endpoints and
``session_maneuvers`` start points, which every analysed non-sensor session
has, whether or not it produced tack/gybe observations of its own. It
approximates — generously — the up-to-six waypoints ``write_wind_cache``
samples, which are not stored: a session can be marked for an observation
just beyond its sampled waypoints, which costs one refresh that changes
nothing and, being one generation, marks nobody.
"""

import logging
import math
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..repositories import get_repos
from . import ingestion, nav_source
from .geo import haversine_m
from .wind_lookup import TRACK_OBS_RADIUS_KM, TRACK_OBS_TIME_PAD

logger = logging.getLogger(__name__)

AUTO_REFRESH_DEBOUNCE = timedelta(minutes=15)
AUTO_REFRESH_COOLDOWN = timedelta(hours=6)
AUTO_REFRESH_MAX_PER_RUN = 3
# A mark nobody has renewed for this long is dropped: with the cooldown that
# is ~8 failed attempts, after which the session waits for a fresh mark.
AUTO_REFRESH_GIVE_UP = timedelta(days=2)
# How long a pending flag still identifies "this upsert is the auto refresh's
# answer". Comfortably above WORKER_TIMEOUT_SEC; a flag older than this was a
# dispatch that never called back and must not swallow a later user run.
AUTO_REFRESH_FLAG_TTL = timedelta(hours=1)
# Slack between two refreshes: the previous analysis's upsert schedules an
# activity-thumbnail dispatch a few seconds after it lands, which must not
# overlap the next analysis dispatch on the same single-invocation worker.
AUTO_REFRESH_PAUSE_S = 15

_KM_PER_DEG_LAT = 111.32
_run_gate = threading.Lock()


def enabled() -> bool:
    """Kill switch, read at call time so it can be flipped without a code
    change: ``WIND_AUTO_REFRESH_ENABLED=0`` stops both marking and refreshing."""
    value = os.environ.get("WIND_AUTO_REFRESH_ENABLED", "1").strip().lower()
    return value not in ("0", "false", "no", "off")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# --- marking -----------------------------------------------------------------

def mark_neighbours(session_id: uuid.UUID, changed: "list[dict]", *,
                    now: Optional[datetime] = None) -> "list[uuid.UUID]":
    """Stamp every other session that would pick up any of ``changed`` in its
    wind cache — within ``TRACK_OBS_RADIUS_KM`` of one of its track points and
    inside its window padded by ``TRACK_OBS_TIME_PAD``, the same criterion
    ``gather_raw_wind`` applies — as stale. Returns the ids marked."""
    if not changed or not enabled():
        return []
    times = [_aware(o["observed_at"]) for o in changed]
    lats = [o["lat"] for o in changed]
    lngs = [o["lng"] for o in changed]
    dlat = TRACK_OBS_RADIUS_KM / _KM_PER_DEG_LAT
    widest = max(abs(min(lats)), abs(max(lats))) + dlat
    dlng = TRACK_OBS_RADIUS_KM / (_KM_PER_DEG_LAT * max(math.cos(math.radians(widest)), 0.01))
    points = get_repos().sessions.wind_neighbour_points(
        exclude_session_id=session_id,
        lat_min=min(lats) - dlat, lat_max=max(lats) + dlat,
        lng_min=min(lngs) - dlng, lng_max=max(lngs) + dlng,
        t_min=min(times) - TRACK_OBS_TIME_PAD, t_max=max(times) + TRACK_OBS_TIME_PAD,
    )
    hits: set = set()
    for sid, started, ended, lat, lng in points:
        if sid in hits:
            continue
        lo = _aware(started) - TRACK_OBS_TIME_PAD
        hi = _aware(ended or started) + TRACK_OBS_TIME_PAD
        for o, t in zip(changed, times):
            if lo <= t <= hi and haversine_m(lat, lng, o["lat"], o["lng"]) / 1000 <= TRACK_OBS_RADIUS_KM:
                hits.add(sid)
                break
    marked = sorted(hits, key=str)
    if marked:
        get_repos().sessions.mark_wind_stale(marked, now or _utcnow())
        logger.info("session %s: wind observations changed, marked %d neighbour(s) stale",
                    session_id, len(marked))
    return marked


def consume_auto_flag(session_id: uuid.UUID, *, now: Optional[datetime] = None) -> bool:
    """Called on every analysis upsert: ``True`` when this analysis is the
    answer to an automatic refresh (so it must mark nobody). Consuming it also
    clears the session's stale mark, unless a newer mark arrived while the
    refresh ran. Best-effort: a failure reads as "not automatic"."""
    try:
        repos = get_repos()
        flagged = repos.sessions.pop_wind_auto_refresh_flag(session_id)
        if flagged is None:
            return False
        flagged = _aware(flagged)
        if (now or _utcnow()) - flagged > AUTO_REFRESH_FLAG_TTL:
            return False
        repos.sessions.clear_wind_stale_not_after(session_id, flagged)
        return True
    except Exception:
        logger.warning("wind auto-refresh flag not read for session %s", session_id,
                       exc_info=True)
        return False


# --- processing --------------------------------------------------------------

def run_pending(*, now: Optional[datetime] = None) -> dict:
    """Refresh up to ``AUTO_REFRESH_MAX_PER_RUN`` stale sessions, one after
    another. A no-op (``{"skipped": ...}``) when disabled or when a run is
    already in progress in this process."""
    if not enabled():
        return {"skipped": "disabled"}
    if not _run_gate.acquire(blocking=False):
        return {"skipped": "busy"}
    try:
        return _run(now or _utcnow())
    finally:
        _run_gate.release()


def _run(now: datetime) -> dict:
    repos = get_repos()
    dropped = repos.sessions.drop_wind_stale_before(now - AUTO_REFRESH_GIVE_UP)
    # Over-fetch: a candidate whose upload is busy with a user's reanalysis is
    # skipped without spending one of the run's slots.
    candidates = repos.sessions.list_wind_stale(
        stale_before=now - AUTO_REFRESH_DEBOUNCE,
        cooldown_before=now - AUTO_REFRESH_COOLDOWN,
        limit=AUTO_REFRESH_MAX_PER_RUN * 4,
    )
    refreshed, failed, skipped = [], [], []
    for session in candidates:
        if len(refreshed) + len(failed) >= AUTO_REFRESH_MAX_PER_RUN:
            break
        upload = nav_source.resolve_nav_upload(session.id)
        if upload is None:
            repos.sessions.set_wind_refresh_state(session.id, wind_stale_at=None)
            skipped.append(session.id)
            continue
        if upload.reanalysis_status == "running":
            skipped.append(session.id)
            continue
        if refreshed or failed:
            time.sleep(AUTO_REFRESH_PAUSE_S)
        if _refresh_one(repos, session.id, upload.id):
            refreshed.append(session.id)
        else:
            failed.append(session.id)
    return {"refreshed": [str(s) for s in refreshed], "failed": [str(s) for s in failed],
            "skipped": [str(s) for s in skipped], "dropped": dropped}


def _refresh_one(repos, session_id: uuid.UUID, upload_id: uuid.UUID) -> bool:
    """One refresh. The cooldown and the one-generation flag are stamped
    *before* dispatch, so a refresh that fails — or never calls back — is not
    retried on the next tick. The stale mark is cleared by the analysis
    upsert that consumes the flag, not here: ``dispatch_analysis`` swallows
    worker errors, so returning is no proof the analysis landed."""
    attempt_at = _utcnow()
    repos.sessions.set_wind_refresh_state(session_id, wind_auto_refreshed_at=attempt_at,
                                          wind_auto_refresh_pending_at=attempt_at)
    # Shares the user-facing reanalysis guard: a user click meanwhile gets a
    # 409 instead of racing this run on wind_cache.json/analysis.json.
    repos.ingest.set_reanalysis_status(upload_id, "running", error=None)
    try:
        ingestion.refresh_wind_cache(session_id)
        return True
    except ValueError:
        # Nothing to refresh from (no track) — permanent, stop asking.
        logger.info("wind auto-refresh: session %s has nothing to refresh", session_id)
        repos.sessions.set_wind_refresh_state(session_id, wind_stale_at=None,
                                              wind_auto_refresh_pending_at=None)
        return False
    except Exception:
        logger.warning("wind auto-refresh failed for session %s", session_id, exc_info=True)
        return False
    finally:
        repos.ingest.set_reanalysis_status(upload_id, None)
