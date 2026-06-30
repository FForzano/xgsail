"""SQL boat catalog repository."""

from typing import Optional

from sqlalchemy import select

from ... import domain
from ...db.models import BoatORM
from ..base import BoatRepo
from . import _mappers as M


class SqlBoatRepo(BoatRepo):
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self) -> list[domain.Boat]:
        with self.Session() as s:
            return [M.boat_to_domain(b) for b in s.scalars(select(BoatORM)).all()]

    def get(self, boat_id: str) -> Optional[domain.Boat]:
        with self.Session() as s:
            orm = s.get(BoatORM, boat_id)
            return M.boat_to_domain(orm) if orm else None

    def save(self, boat: domain.Boat) -> domain.Boat:
        with self.Session() as s:
            orm = s.get(BoatORM, boat.boat_id)
            if orm is None:
                orm = BoatORM(boat_id=boat.boat_id)
                s.add(orm)
            M.apply_boat(orm, boat)
            s.commit()
        return boat

    def delete(self, boat_id: str) -> bool:
        with self.Session() as s:
            orm = s.get(BoatORM, boat_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True
