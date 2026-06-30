"""SQL race repository (aggregate with marks/boats/result children)."""

from typing import Optional

from sqlalchemy import select

from ... import domain
from ...db.models import RaceORM
from ..base import RaceRepo
from . import _mappers as M


class SqlRaceRepo(RaceRepo):
    def __init__(self, session_factory):
        self.Session = session_factory

    def list_summaries(self, *, regatta_id=None, date=None, raceday_id=None) -> list[dict]:
        with self.Session() as s:
            stmt = select(RaceORM)
            if regatta_id:
                stmt = stmt.where(RaceORM.regatta_id == regatta_id)
            if date:
                stmt = stmt.where(RaceORM.date == date)
            if raceday_id:
                stmt = stmt.where(RaceORM.raceday_id == raceday_id)
            return [M.race_to_summary(r) for r in s.scalars(stmt).all()]

    def get(self, race_id: str) -> Optional[domain.Race]:
        with self.Session() as s:
            orm = s.get(RaceORM, race_id)
            return M.race_to_domain(orm) if orm else None

    def save(self, race: domain.Race) -> domain.Race:
        with self.Session() as s:
            orm = s.get(RaceORM, race.race_id)
            if orm is None:
                orm = RaceORM(race_id=race.race_id)
                s.add(orm)
            M.apply_race(orm, race)
            s.commit()
        return race

    def delete(self, race_id: str) -> bool:
        with self.Session() as s:
            orm = s.get(RaceORM, race_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True
