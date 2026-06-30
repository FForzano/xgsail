"""Object-storage boat catalog repository — ``{DATA_PREFIX}/boats.json``."""

from typing import Optional

from ... import domain
from ...storage import BlobStore
from ..base import BoatRepo
from ._common import load_index


class ObjectBoatRepo(BoatRepo):
    def __init__(self, blob: BlobStore, data_prefix: str):
        self.blob = blob
        self.key = f"{data_prefix}/boats.json"

    def list(self) -> list[domain.Boat]:
        data = load_index(self.blob, self.key)
        return [domain.Boat.from_dict(b) for b in data.get("boats", [])]

    def get(self, boat_id: str) -> Optional[domain.Boat]:
        for b in self.list():
            if b.boat_id == boat_id:
                return b
        return None

    def save(self, boat: domain.Boat) -> domain.Boat:
        data = load_index(self.blob, self.key) or {"boats": []}
        items = data.get("boats", [])
        for i, b in enumerate(items):
            if b.get("boat_id") == boat.boat_id:
                items[i] = boat.to_dict()
                break
        else:
            items.append(boat.to_dict())
        data["boats"] = items
        self.blob.put_json(self.key, data)
        return boat

    def delete(self, boat_id: str) -> bool:
        data = load_index(self.blob, self.key) or {"boats": []}
        items = data.get("boats", [])
        new_items = [b for b in items if b.get("boat_id") != boat_id]
        if len(new_items) == len(items):
            return False
        data["boats"] = new_items
        self.blob.put_json(self.key, data)
        return True
