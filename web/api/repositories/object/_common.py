"""Shared helpers + index key constants for the object-storage repositories."""

from ... import domain
from ...storage import BlobStore, BlobNotFound

RACES_INDEX_KEY = "races/races.json"
REGATTAS_INDEX_KEY = "regattas/regattas.json"
RACEDAYS_INDEX_KEY = "racedays/racedays.json"

# User-system entities (no-DB deploy). One index JSON per aggregate.
USERS_INDEX_KEY = "meta/users.json"
AUTH_TOKENS_INDEX_KEY = "meta/auth_tokens.json"
CLUBS_INDEX_KEY = "meta/clubs.json"
GROUPS_INDEX_KEY = "meta/groups.json"
DEVICES_INDEX_KEY = "meta/devices.json"


def next_int_id(items: list[dict], field: str = "id") -> int:
    """Next autoincrement-style int id for a JSON index list."""
    return max((int(it.get(field) or 0) for it in items), default=0) + 1


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
