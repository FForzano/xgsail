"""Object-storage race repository.

Full record per race at ``races/{id}/race.json`` plus a lightweight summary in
the shared ``races/races.json`` index (matching the historical layout).
"""

from typing import Optional

from ... import domain
from ...storage import BlobStore
from ..base import RaceRepo
from ._common import RACES_INDEX_KEY, load_index, race_summary


class ObjectRaceRepo(RaceRepo):
    def __init__(self, blob: BlobStore):
        self.blob = blob

    def _race_key(self, race_id: str) -> str:
        return f"races/{race_id}/race.json"

    def list_summaries(self, *, regatta_id=None, date=None, raceday_id=None) -> list[dict]:
        data = load_index(self.blob, RACES_INDEX_KEY)
        races = data.get("races", [])
        if regatta_id:
            races = [r for r in races if r.get("regatta_id") == regatta_id]
        if date:
            races = [r for r in races if r.get("date") == date]
        if raceday_id:
            races = [r for r in races if r.get("raceday_id") == raceday_id]
        return races

    def get(self, race_id: str) -> Optional[domain.Race]:
        data = load_index(self.blob, self._race_key(race_id))
        if not data:
            return None
        return domain.Race.from_dict(data)

    def save(self, race: domain.Race) -> domain.Race:
        self.blob.put_json(self._race_key(race.race_id), race.to_dict())
        index = load_index(self.blob, RACES_INDEX_KEY) or {"races": []}
        items = index.get("races", [])
        summary = race_summary(race)
        for i, r in enumerate(items):
            if r.get("race_id") == race.race_id:
                items[i] = summary
                break
        else:
            items.append(summary)
        index["races"] = items
        self.blob.put_json(RACES_INDEX_KEY, index)
        return race

    def delete(self, race_id: str) -> bool:
        existed = bool(load_index(self.blob, self._race_key(race_id)))
        self.blob.delete(self._race_key(race_id))
        try:
            self.blob.delete(f"races/{race_id}/results.json")
        except Exception:
            pass
        index = load_index(self.blob, RACES_INDEX_KEY) or {"races": []}
        items = index.get("races", [])
        new_items = [r for r in items if r.get("race_id") != race_id]
        if len(new_items) != len(items):
            index["races"] = new_items
            self.blob.put_json(RACES_INDEX_KEY, index)
            existed = True
        return existed
