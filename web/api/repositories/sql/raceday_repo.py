"""SQL race-day repository."""

from typing import Optional

from sqlalchemy import select

from ... import domain
from ...db.models import RaceDayORM
from ..base import RaceDayRepo
from . import _mappers as M


class SqlRaceDayRepo(RaceDayRepo):
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self) -> list[domain.RaceDay]:
        with self.Session() as s:
            return [M.raceday_to_domain(r) for r in s.scalars(select(RaceDayORM)).all()]

    def get(self, raceday_id: str) -> Optional[domain.RaceDay]:
        with self.Session() as s:
            orm = s.get(RaceDayORM, raceday_id)
            return M.raceday_to_domain(orm) if orm else None

    def save(self, raceday: domain.RaceDay) -> domain.RaceDay:
        with self.Session() as s:
            orm = s.get(RaceDayORM, raceday.raceday_id)
            if orm is None:
                orm = RaceDayORM(raceday_id=raceday.raceday_id)
                s.add(orm)
            M.apply_raceday(orm, raceday)
            s.commit()
        return raceday

    def delete(self, raceday_id: str) -> bool:
        with self.Session() as s:
            orm = s.get(RaceDayORM, raceday_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True
