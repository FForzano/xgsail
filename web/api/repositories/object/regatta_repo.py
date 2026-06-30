"""Object-storage regatta repository — ``regattas/regattas.json``."""

from typing import Optional

from ... import domain
from ...storage import BlobStore
from ..base import RegattaRepo
from ._common import REGATTAS_INDEX_KEY, load_index


class ObjectRegattaRepo(RegattaRepo):
    def __init__(self, blob: BlobStore):
        self.blob = blob

    def list(self) -> list[domain.Regatta]:
        data = load_index(self.blob, REGATTAS_INDEX_KEY)
        return [domain.Regatta.from_dict(r) for r in data.get("regattas", [])]

    def get(self, regatta_id: str) -> Optional[domain.Regatta]:
        for r in self.list():
            if r.regatta_id == regatta_id:
                return r
        return None

    def save(self, regatta: domain.Regatta) -> domain.Regatta:
        data = load_index(self.blob, REGATTAS_INDEX_KEY) or {"regattas": []}
        items = data.get("regattas", [])
        for i, r in enumerate(items):
            if r.get("regatta_id") == regatta.regatta_id:
                items[i] = regatta.to_dict()
                break
        else:
            items.append(regatta.to_dict())
        data["regattas"] = items
        self.blob.put_json(REGATTAS_INDEX_KEY, data)
        return regatta

    def delete(self, regatta_id: str) -> bool:
        data = load_index(self.blob, REGATTAS_INDEX_KEY) or {"regattas": []}
        items = data.get("regattas", [])
        new_items = [r for r in items if r.get("regatta_id") != regatta_id]
        if len(new_items) == len(items):
            return False
        data["regattas"] = new_items
        self.blob.put_json(REGATTAS_INDEX_KEY, data)
        return True
