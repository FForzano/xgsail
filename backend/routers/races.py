"""Race endpoints (``/api/races``): CRUD + per-boat results + compute.

Structure: race_days -> races; per-boat results (unique per race+boat). The
tracked data of a race lives on ITS activity (``activities.race_id``,
implicitly created on first use) whose sessions supply the GPS streams for the
compute endpoints (race data, match-sessions, auto start line, mark
suggestion). Guards: pub reads; writes scoped ``race.manage``/``result.manage``
via the regatta's club; marks via ``mark.manage``.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile

from ..auth import require_permission, require_user, verify_csrf
from ..schemas import RaceWriteModel, ResultWriteModel
from ..services import course as course_service
from ..services import gpx as gpx_service
from ..services import ingestion
from ..storage import BlobNotFound
from ._common import blob, repos

router = APIRouter(prefix="/api/races", tags=["races"])

DEFAULT_RACE_WINDOW_HOURS = 4


def _require_race(race_id: uuid.UUID):
    race = repos.races.get(race_id)
    if race is None:
        raise HTTPException(404, "Race not found")
    return race


def _require_manage(request: Request, race_id: uuid.UUID, key: str = "race.manage") -> None:
    require_permission(request, key, club_id=repos.races.club_id_for_race(race_id))


def _race_activity(race, *, create: bool = False):
    """THE activity tracking this race (activities.race_id), created lazily."""
    activity = repos.activities.get_by_race(race.id)
    if activity is not None or not create:
        return activity
    started = race.start_time
    ended = started + timedelta(hours=DEFAULT_RACE_WINDOW_HOURS) if started else None
    return repos.activities.create({
        "name": f"Race {race.race_number}",
        "type": "race",
        "race_id": race.id,
        "club_id": repos.races.club_id_for_race(race.id),
        "visibility": "public",
        "started_at": started,
        "ended_at": ended,
    })


def _parse_point_t(t: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _window_filter(points: list[dict], start: Optional[datetime],
                   end: Optional[datetime]) -> list[dict]:
    if start is None and end is None:
        return points
    out = []
    for p in points:
        ts = _parse_point_t(p.get("t", ""))
        if ts is None:
            continue
        if start is not None and ts < start:
            continue
        if end is not None and ts > end:
            continue
        out.append(p)
    return out


def _session_gps(session_id: uuid.UUID, sensor_type: str = "gps") -> list[dict]:
    for stream in repos.ingest.list_streams_for_session(session_id):
        if stream.sensor_type == sensor_type and stream.data_ref:
            try:
                return blob.get_json(stream.data_ref)
            except BlobNotFound:
                continue
    return []


def _race_boat_gps(race) -> tuple[dict, "object"]:
    """``{session_id: [gps points]}`` for the race activity, window-filtered."""
    activity = _race_activity(race)
    if activity is None:
        raise HTTPException(409, "No tracked sessions for this race yet")
    boat_gps = {}
    for session in repos.sessions.list(activity_id=activity.id):
        points = _window_filter(_session_gps(session.id),
                                activity.started_at, activity.ended_at)
        if points:
            boat_gps[str(session.id)] = points
    return boat_gps, activity


# --- CRUD -------------------------------------------------------------------

@router.get("")
def list_races(race_day_id: Optional[uuid.UUID] = None):
    return [r.to_dict() for r in repos.races.list(race_day_id=race_day_id)]


@router.get("/{race_id}")
def get_race(race_id: uuid.UUID):
    race = _require_race(race_id)
    d = race.to_dict()
    activity = _race_activity(race)
    d["activity_id"] = activity.id if activity else None
    d["results"] = [r.to_dict() for r in repos.races.list_results(race_id)]
    return d


@router.post("")
def create_race(body: RaceWriteModel, request: Request):
    verify_csrf(request)
    if body.race_day_id is None or body.race_number is None:
        raise HTTPException(422, "race_day_id and race_number are required")
    raceday = repos.racedays.get(body.race_day_id)
    if raceday is None:
        raise HTTPException(404, "Race day not found")
    require_permission(request, "race.manage",
                       club_id=repos.racedays.club_id_for_raceday(body.race_day_id))
    return repos.races.create(body.model_dump(exclude_unset=True)).to_dict()


@router.patch("/{race_id}")
def update_race(race_id: uuid.UUID, body: RaceWriteModel, request: Request):
    verify_csrf(request)
    _require_race(race_id)
    _require_manage(request, race_id)
    changes = body.model_dump(exclude_unset=True)
    changes.pop("race_day_id", None)  # a race doesn't move between days
    return repos.races.update(race_id, changes).to_dict()


@router.delete("/{race_id}")
def delete_race(race_id: uuid.UUID, request: Request):
    verify_csrf(request)
    _require_race(race_id)
    _require_manage(request, race_id)
    repos.races.delete(race_id)
    return {"ok": True}


# --- results (one row per boat) -----------------------------------------------

@router.get("/{race_id}/results")
def list_results(race_id: uuid.UUID):
    _require_race(race_id)
    return [r.to_dict() for r in repos.races.list_results(race_id)]


@router.put("/{race_id}/results/{boat_id}")
def upsert_result(race_id: uuid.UUID, boat_id: uuid.UUID,
                  body: ResultWriteModel, request: Request):
    verify_csrf(request)
    _require_race(race_id)
    _require_manage(request, race_id, key="result.manage")
    if repos.boats.get(boat_id) is None:
        raise HTTPException(404, "Boat not found")
    return repos.races.upsert_result(race_id, boat_id,
                                     body.model_dump(exclude_unset=True)).to_dict()


@router.delete("/{race_id}/results/{boat_id}")
def delete_result(race_id: uuid.UUID, boat_id: uuid.UUID, request: Request):
    verify_csrf(request)
    _require_race(race_id)
    _require_manage(request, race_id, key="result.manage")
    if not repos.races.delete_result(race_id, boat_id):
        raise HTTPException(404, "Result not found")
    return {"ok": True}


# --- compute --------------------------------------------------------------------

@router.get("/{race_id}/data")
def get_race_data(race_id: uuid.UUID, sensors: str = "gps",
                  pad_start: int = 0, pad_end: int = 0):
    """Time-aligned sensor data of every session in the race activity, keyed
    by session id with boat info embedded."""
    race = _require_race(race_id)
    activity = _race_activity(race)
    if activity is None:
        return {"race_id": race_id, "sessions": {}}
    start = activity.started_at - timedelta(seconds=pad_start) if activity.started_at else None
    end = activity.ended_at + timedelta(seconds=pad_end) if activity.ended_at else None

    wanted = [s.strip() for s in sensors.split(",") if s.strip()]
    out = {}
    for session in repos.sessions.list(activity_id=activity.id):
        boat = repos.boats.get(session.boat_id)
        entry = {
            "session_id": session.id,
            "boat": {"id": boat.id, "name": boat.name, "sail_number": boat.sail_number}
            if boat else None,
            "sensors": {},
        }
        for stream in repos.ingest.list_streams_for_session(session.id):
            if stream.sensor_type not in wanted or not stream.data_ref:
                continue
            try:
                points = blob.get_json(stream.data_ref)
            except BlobNotFound:
                continue
            entry["sensors"][stream.sensor_type] = _window_filter(points, start, end)
        out[str(session.id)] = entry
    return {"race_id": race_id, "activity_id": activity.id, "sessions": out}


@router.post("/{race_id}/match-sessions")
def match_sessions(race_id: uuid.UUID, request: Request):
    """Re-parent the best time-overlapping session of each boat into the race
    activity (the sessions were recorded as solo outings by the devices)."""
    verify_csrf(request)
    _require_manage(request, race_id)
    race = _require_race(race_id)
    activity = _race_activity(race, create=True)
    if activity.started_at is None:
        raise HTTPException(409, "Set race start_time (or activity bounds) first")
    start = activity.started_at
    end = activity.ended_at or start + timedelta(hours=DEFAULT_RACE_WINDOW_HOURS)

    def overlap(s) -> float:
        s_start = s.started_at
        s_end = s.ended_at or s.started_at
        if s_start is None:
            return 0.0
        latest = max(start, s_start)
        earliest = min(end, s_end)
        return max(0.0, (earliest - latest).total_seconds())

    best_per_boat: dict = {}
    for session in repos.sessions.list():
        if session.activity_id == activity.id:
            continue
        sec = overlap(session)
        if sec <= 0:
            continue
        current = best_per_boat.get(session.boat_id)
        if current is None or sec > current[1]:
            best_per_boat[session.boat_id] = (session, sec)

    matched = []
    for session, sec in best_per_boat.values():
        repos.sessions.update(session.id, {"activity_id": activity.id})
        repos.sessions.extend_window(session.id, session.started_at, session.ended_at)
        matched.append({"session_id": session.id, "boat_id": session.boat_id,
                        "overlap_s": sec})
    return {"activity_id": activity.id, "matched": matched}


@router.post("/{race_id}/auto-start-line")
def auto_start_line(race_id: uuid.UUID, request: Request, apply: bool = False):
    verify_csrf(request)
    _require_manage(request, race_id, key="mark.manage")
    race = _require_race(race_id)
    if race.start_time is None:
        raise HTTPException(409, "Race has no start_time")
    boat_gps, activity = _race_boat_gps(race)
    if not boat_gps:
        raise HTTPException(409, "No GPS data in the race window")
    try:
        line = course_service.estimate_start_line(
            boat_gps, race.start_time.isoformat().replace("+00:00", "Z"))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if apply:
        for role, pt in (("pin", line.get("pin")), ("rc", line.get("rc"))):
            if pt:
                repos.activities.add_mark(activity.id, {
                    "mark_role": role, "lat": pt["lat"], "lng": pt.get("lon", pt.get("lng")),
                    "set_at": race.start_time,
                })
    return line


@router.post("/{race_id}/suggest-marks")
def suggest_marks(race_id: uuid.UUID, request: Request, apply: bool = False):
    verify_csrf(request)
    _require_manage(request, race_id, key="mark.manage")
    race = _require_race(race_id)
    boat_gps, activity = _race_boat_gps(race)
    if not boat_gps:
        raise HTTPException(409, "No GPS data in the race window")
    suggestion = course_service.detect_marks(boat_gps)
    if apply and suggestion.get("marks"):
        repos.activities.replace_marks(activity.id, [
            {"mark_role": m.get("mark_role", "drill"),
             "lat": m["lat"], "lng": m.get("lon", m.get("lng"))}
            for m in suggestion["marks"]
        ])
    return suggestion


@router.get("/{race_id}/ais")
def get_ais(race_id: uuid.UUID):
    """AIS overlay passthrough (vessels.json written by an external collector)."""
    _require_race(race_id)
    try:
        return blob.get_json(f"races/{race_id}/ais/vessels.json")
    except BlobNotFound:
        return {"vessels": []}


@router.post("/{race_id}/boats/{boat_id}/gpx")
async def upload_boat_gpx(race_id: uuid.UUID, boat_id: uuid.UUID,
                          file: UploadFile, request: Request):
    """Attach a GPX track of a boat to the race: parsed inline and registered
    as a manual-import session_upload on the race activity's session."""
    verify_csrf(request)
    user = require_user(request)
    _require_manage(request, race_id)
    race = _require_race(race_id)
    if repos.boats.get(boat_id) is None:
        raise HTTPException(404, "Boat not found")
    content = await file.read()
    try:
        points = gpx_service.parse_gpx(content)
    except Exception:
        raise HTTPException(422, "Could not parse GPX file")
    if not points:
        raise HTTPException(422, "GPX contains no timestamped points")

    activity = _race_activity(race, create=True)
    started = _parse_point_t(points[0]["t"])
    ended = _parse_point_t(points[-1]["t"])
    session = ingestion.find_or_create_session(
        boat_id=boat_id, started_at=started, ended_at=ended,
        activity_id=activity.id, created_by=user.id,
    )
    import_row = repos.ingest.create_import(
        uploaded_by=user.id, original_filename=file.filename or "track.gpx")
    upload = repos.ingest.create_upload({
        "session_id": session.id, "source_type": "manual_import",
        "import_id": import_row.id, "subject_type": "boat", "status": "processing",
    })
    raw_key = ingestion.upload_raw_key(upload.id, import_row.original_filename)
    blob.put_bytes(raw_key, content, content_type="application/gpx+xml")
    repos.ingest.update_upload(upload.id, {"raw_ref": raw_key})
    data_ref = f"{ingestion.processed_prefix(upload.id)}gps.json"
    blob.put_json(data_ref, points)
    repos.ingest.upsert_streams(upload.id, [{
        "sensor_type": "gps", "data_ref": data_ref, "row_count": len(points),
    }])
    repos.ingest.set_upload_status(upload.id, "processed")
    repos.ingest.update_import(import_row.id, {"status": "processed"})
    repos.sessions.rollup_status(session.id)
    return {"session_id": session.id, "session_upload_id": upload.id,
            "points": len(points)}
