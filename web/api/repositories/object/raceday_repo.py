"""Object-storage race-day repository — ``racedays/racedays.json``."""

from typing import Optional

from ... import domain
from ...storage import BlobStore
from ..base import RaceDayRepo
from ._common import RACEDAYS_INDEX_KEY, load_index


class ObjectRaceDayRepo(RaceDayRepo):
    def __init__(self, blob: BlobStore):
        self.blob = blob

    def list(self) -> list[domain.RaceDay]:
        data = load_index(self.blob, RACEDAYS_INDEX_KEY)
        return [domain.RaceDay.from_dict(d) for d in data.get("race_days", [])]

    def get(self, raceday_id: str) -> Optional[domain.RaceDay]:
        for d in self.list():
            if d.raceday_id == raceday_id:
                return d
        return None

    def save(self, raceday: domain.RaceDay) -> domain.RaceDay:
        data = load_index(self.blob, RACEDAYS_INDEX_KEY) or {"race_days": []}
        items = data.get("race_days", [])
        for i, d in enumerate(items):
            if d.get("raceday_id") == raceday.raceday_id:
                items[i] = raceday.to_dict()
                break
        else:
            items.append(raceday.to_dict())
        data["race_days"] = items
        self.blob.put_json(RACEDAYS_INDEX_KEY, data)
        return raceday

    def delete(self, raceday_id: str) -> bool:
        data = load_index(self.blob, RACEDAYS_INDEX_KEY) or {"race_days": []}
        items = data.get("race_days", [])
        new_items = [d for d in items if d.get("raceday_id") != raceday_id]
        if len(new_items) == len(items):
            return False
        data["race_days"] = new_items
        self.blob.put_json(RACEDAYS_INDEX_KEY, data)
        return True
