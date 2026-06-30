"""Race endpoints (``/api/races*``).

A race owns its course (marks), entrants (boats), start/finish lines and
computed results. This router also hosts the race sub-resources: time-aligned
multi-boat data, session matching, per-boat GPX upload, and the start-line /
marks auto-suggestion. Cross-entity bookkeeping (linking a race into its race
day / regatta) goes through the repository layer.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from .. import domain
from ..auth import require_admin
from ..schemas import RaceCreateModel, RaceUpdateModel
from ..services import course, geo, gpx
from ._common import (
    blob,
    get_race_dict,
    load_json_or_empty,
    now_iso,
    repos,
    save_json,
    save_race_dict,
)

router = APIRouter(prefix="/api/races", tags=["races"])


# --- Local helpers --------------------------------------------------------

def _find_device_sessions(device_id: str, date: str) -> list[dict]:
    """Find all sessions for a device on a given date."""
    sessions = []

    # Look for manifest files in processed folder
    prefix = f"processed/{device_id}/{date}"

    for key in blob.list_keys(prefix):
        if not key.endswith("/manifest.json"):
            continue
        try:
            manifest = blob.get_json(key)
            # Extract session folder from key (.../{session_folder}/manifest.json)
            session_folder = key.split("/")[-2]
            sessions.append({
                "session_path": f"{date}/{session_folder}",
                "start_time": manifest.get("start_time", ""),
                "end_time": manifest.get("end_time", ""),
            })
        except Exception:
            pass

    return sessions


def _load_race_gps(race_data: dict) -> dict:
    """Return ``{device_id: [gps_points]}`` for all boats with session data,
    filtered to the race window. GPS series live in the blob store."""
    start_time = race_data["start_time"]
    end_time = race_data["end_time"]
    out = {}
    for boat in race_data.get("boats", []):
        device_id = boat["device_id"]
        session_path = boat.get("session_path")
        if not session_path:
            continue
        key = f"processed/{device_id}/{session_path}/gps.json"
        data = load_json_or_empty(key)
        if not isinstance(data, list):
            continue
        filtered = [d for d in data if start_time <= d.get("t", "") <= end_time]
        if filtered:
            out[device_id] = filtered
    return out


# --- Race CRUD ------------------------------------------------------------

@router.get("")
def list_races(regatta_id: Optional[str] = None, date: Optional[str] = None, raceday_id: Optional[str] = None):
    """List all races, optionally filtered by regatta, date, or race day."""
    races = repos.races.list_summaries(regatta_id=regatta_id, date=date, raceday_id=raceday_id)
    return {"races": sorted(races, key=lambda r: (r.get("date", ""), r.get("start_time", "")))}


@router.get("/{race_id}")
def get_race(race_id: str):
    """Get a single race by ID."""
    race = repos.races.get(race_id)
    if race is None:
        raise HTTPException(404, f"Race not found: {race_id}")
    return race.to_dict()


@router.post("")
def create_race(race: RaceCreateModel, request: Request):
    """Create a new race."""
    require_admin(request)
    now = now_iso()
    new_race = domain.Race(
        race_id=str(uuid.uuid4())[:8],
        name=race.name,
        date=race.date,
        start_time=race.start_time,
        end_time=race.end_time,
        regatta_id=race.regatta_id,
        raceday_id=race.raceday_id,
        boats=[domain.RaceBoat.from_dict(b.model_dump()) for b in race.boats],
        start_line=domain.StartFinishLine.from_dict(race.start_line.model_dump()) if race.start_line else None,
        finish_line=domain.StartFinishLine.from_dict(race.finish_line.model_dump()) if race.finish_line else None,
        marks=[domain.Mark.from_dict(m.model_dump()) for m in race.marks],
        course=race.course,
        finish_order=race.finish_order,
        results=None,
        created_at=now,
        updated_at=now,
    )
    repos.races.save(new_race)

    # Link race into its race day / regatta (cross-entity bookkeeping).
    if race.raceday_id:
        day = repos.racedays.get(race.raceday_id)
        if day and new_race.race_id not in day.race_ids:
            day.race_ids.append(new_race.race_id)
            day.updated_at = now
            repos.racedays.save(day)

    if race.regatta_id:
        regatta = repos.regattas.get(race.regatta_id)
        if regatta and new_race.race_id not in regatta.race_ids:
            regatta.race_ids.append(new_race.race_id)
            regatta.updated_at = now
            repos.regattas.save(regatta)

    return new_race.to_dict()


@router.patch("/{race_id}")
def update_race(race_id: str, update: RaceUpdateModel, request: Request):
    """Update a race."""
    require_admin(request)
    race = repos.races.get(race_id)
    if race is None:
        raise HTTPException(404, f"Race not found: {race_id}")

    if update.name is not None:
        race.name = update.name
    if update.start_time is not None:
        race.start_time = update.start_time
    if update.end_time is not None:
        race.end_time = update.end_time
    if update.boats is not None:
        race.boats = [domain.RaceBoat.from_dict(b.model_dump()) for b in update.boats]
    if update.start_line is not None:
        race.start_line = domain.StartFinishLine.from_dict(update.start_line.model_dump())
    if update.finish_line is not None:
        race.finish_line = domain.StartFinishLine.from_dict(update.finish_line.model_dump())
    if update.marks is not None:
        race.marks = [domain.Mark.from_dict(m.model_dump()) for m in update.marks]
    if update.course is not None:
        race.course = update.course
    if update.finish_order is not None:
        race.finish_order = update.finish_order
    if update.raceday_id is not None:
        race.raceday_id = update.raceday_id or None

    race.updated_at = now_iso()
    repos.races.save(race)
    return race.to_dict()


@router.delete("/{race_id}")
def delete_race(race_id: str, request: Request):
    """Delete a race."""
    require_admin(request)
    race = repos.races.get(race_id)
    if race is None:
        raise HTTPException(404, f"Race not found: {race_id}")

    repos.races.delete(race_id)

    # Unlink from regatta if linked
    if race.regatta_id:
        regatta = repos.regattas.get(race.regatta_id)
        if regatta:
            regatta.race_ids = [rid for rid in regatta.race_ids if rid != race_id]
            regatta.updated_at = now_iso()
            repos.regattas.save(regatta)

    return {"deleted": race_id}


# --- Multi-Boat Data Endpoint ---------------------------------------------

@router.get("/{race_id}/data")
def get_race_data(
    race_id: str,
    sensors: str = Query("gps,imu,wind", description="Comma-separated sensors to load"),
):
    """
    Load time-aligned sensor data for all boats in a race.

    Returns data filtered to race time window for each boat that has
    a matched session.
    """
    race_data = get_race_dict(race_id)
    if not race_data:
        raise HTTPException(404, f"Race not found: {race_id}")

    start_time = race_data["start_time"]
    end_time = race_data["end_time"]
    requested_sensors = [s.strip() for s in sensors.split(",")]

    boats_data = {}

    for boat in race_data.get("boats", []):
        device_id = boat["device_id"]
        session_path = boat.get("session_path")
        gpx_path = boat.get("gpx_path")

        if not session_path and not gpx_path:
            boats_data[device_id] = {"error": "No session matched", "boat": boat}
            continue

        boat_sensors = {}
        for sensor in requested_sensors:
            # GPX upload replaces the GPS sensor for this boat
            if sensor == "gps" and gpx_path:
                try:
                    data = load_json_or_empty(gpx_path)
                    if isinstance(data, list):
                        filtered = [
                            d for d in data
                            if start_time <= d.get("t", "") <= end_time
                        ]
                        boat_sensors[sensor] = filtered
                    else:
                        boat_sensors[sensor] = []
                except Exception as e:
                    boat_sensors[sensor] = {"error": str(e)}
                continue

            if not session_path:
                boat_sensors[sensor] = []
                continue

            try:
                sensor_key = f"processed/{device_id}/{session_path}/{sensor}.json"
                data = load_json_or_empty(sensor_key)
                if isinstance(data, list):
                    filtered = [
                        d for d in data
                        if start_time <= d.get("t", "") <= end_time
                    ]
                    boat_sensors[sensor] = filtered
                else:
                    boat_sensors[sensor] = data
            except Exception as e:
                boat_sensors[sensor] = {"error": str(e)}

        boats_data[device_id] = {
            "boat": boat,
            "sensors": boat_sensors,
        }

    return {
        "race": {
            "race_id": race_id,
            "name": race_data["name"],
            "date": race_data["date"],
            "start_time": start_time,
            "end_time": end_time,
        },
        "boats": boats_data,
        "time_bounds": {
            "start": start_time,
            "end": end_time,
        },
    }


# --- Session Matching -----------------------------------------------------

@router.post("/{race_id}/match-sessions")
def match_sessions_to_race(race_id: str, request: Request):
    """
    Auto-match E1-E6 device sessions to a race based on time overlap.

    Finds sessions from each device that overlap with the race time window
    and updates the race's boat session_path fields.
    """
    require_admin(request)
    race_data = get_race_dict(race_id)
    if not race_data:
        raise HTTPException(404, f"Race not found: {race_id}")

    race_start = race_data["start_time"]
    race_end = race_data["end_time"]
    race_date = race_data["date"]

    matched = []
    for boat in race_data.get("boats", []):
        device_id = boat["device_id"]

        # Find sessions for this device on race date
        try:
            sessions = _find_device_sessions(device_id, race_date)
        except Exception:
            sessions = []

        # Find session with best overlap
        best_session = None
        best_overlap = 0

        for session in sessions:
            session_start = session.get("start_time", "")
            session_end = session.get("end_time", "")

            # Calculate overlap
            overlap_start = max(race_start, session_start)
            overlap_end = min(race_end, session_end)

            if overlap_start < overlap_end:
                # There is overlap
                overlap_duration = geo.iso_diff_seconds(overlap_end, overlap_start)
                if overlap_duration > best_overlap:
                    best_overlap = overlap_duration
                    best_session = session

        if best_session:
            boat["session_path"] = best_session["session_path"]
            matched.append({
                "device_id": device_id,
                "session_path": best_session["session_path"],
                "overlap_sec": best_overlap,
            })
        else:
            matched.append({
                "device_id": device_id,
                "session_path": None,
                "error": "No overlapping session found",
            })

    # Save updated race
    race_data["updated_at"] = now_iso()
    save_race_dict(race_data)

    return {"race_id": race_id, "matched": matched}


@router.post("/{race_id}/boats/{device_id}/gpx")
async def upload_boat_gpx(
    race_id: str, device_id: str, request: Request, file: UploadFile = File(...)
):
    """Upload a GPX track file as the GPS source for a boat in a race."""
    require_admin(request)

    race_data = get_race_dict(race_id)
    if not race_data:
        raise HTTPException(404, f"Race not found: {race_id}")

    boat = next((b for b in race_data.get("boats", []) if b["device_id"] == device_id), None)
    if boat is None:
        raise HTTPException(404, f"Boat {device_id} not found in race {race_id}")

    content = await file.read()
    try:
        track_points = gpx.parse_gpx(content)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse GPX: {e}")

    if not track_points:
        raise HTTPException(400, "GPX file contains no track points")

    gpx_key = f"races/{race_id}/gpx/{device_id}.json"
    save_json(gpx_key, track_points)

    boat["gpx_path"] = gpx_key
    boat["session_path"] = None  # GPX replaces session
    race_data["updated_at"] = now_iso()
    save_race_dict(race_data)

    return {
        "device_id": device_id,
        "gpx_path": gpx_key,
        "points": len(track_points),
        "start_time": track_points[0]["t"],
        "end_time": track_points[-1]["t"],
    }


# --- Auto-Suggest Endpoints -----------------------------------------------

@router.post("/{race_id}/auto-start-line")
def auto_start_line(race_id: str, request: Request):
    """
    Estimate a start line from fleet positions at the gun time.

    Places the line perpendicular to the mean fleet heading, through the fleet
    centroid. Length scales to cover the fleet with 30m padding on each end.
    """
    require_admin(request)
    race_data = get_race_dict(race_id)
    if not race_data:
        raise HTTPException(404, f"Race not found: {race_id}")

    boat_gps = _load_race_gps(race_data)
    if not boat_gps:
        raise HTTPException(400, "No boat session data available for this race")

    try:
        return course.estimate_start_line(boat_gps, race_data["start_time"])
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{race_id}/suggest-marks")
def suggest_marks(race_id: str, request: Request):
    """
    Detect rounding points across boat tracks and cluster them into candidate marks.

    A rounding point is where a boat's course changes by >= 60° within a 30-second
    window. Points within 100m of each other are clustered; each cluster centroid
    becomes a suggested mark, ordered by the average time of the cluster.
    """
    require_admin(request)
    race_data = get_race_dict(race_id)
    if not race_data:
        raise HTTPException(404, f"Race not found: {race_id}")

    boat_gps = _load_race_gps(race_data)
    if not boat_gps:
        raise HTTPException(400, "No boat session data available for this race")

    return course.detect_marks(boat_gps)
