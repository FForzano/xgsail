"""Shared helpers + index key constants for the object-storage repositories."""

from ... import domain
from ...storage import BlobStore, BlobNotFound

RACES_INDEX_KEY = "races/races.json"
REGATTAS_INDEX_KEY = "regattas/regattas.json"
RACEDAYS_INDEX_KEY = "racedays/racedays.json"


def load_index(blob: BlobStore, key: str) -> dict:
    """Read an index JSON, tolerating missing/corrupt files as ``{}``."""
    try:
        return blob.get_json(key)
    except BlobNotFound:
        return {}
    except Exception:
        return {}


def race_summary(race: "domain.Race") -> dict:
    """The lightweight summary entry stored in ``races/races.json``."""
    return {
        "race_id": race.race_id,
        "name": race.name,
        "date": race.date,
        "start_time": race.start_time,
        "end_time": race.end_time,
        "regatta_id": race.regatta_id,
        "raceday_id": race.raceday_id,
        "boat_count": len(race.boats),
    }
