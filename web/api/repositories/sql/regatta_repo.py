"""SQL regatta repository."""

from typing import Optional

from sqlalchemy import select

from ... import domain
from ...db.models import RegattaORM
from ..base import RegattaRepo
from . import _mappers as M


class SqlRegattaRepo(RegattaRepo):
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self) -> list[domain.Regatta]:
        with self.Session() as s:
            return [M.regatta_to_domain(r) for r in s.scalars(select(RegattaORM)).all()]

    def get(self, regatta_id: str) -> Optional[domain.Regatta]:
        with self.Session() as s:
            orm = s.get(RegattaORM, regatta_id)
            return M.regatta_to_domain(orm) if orm else None

    def save(self, regatta: domain.Regatta) -> domain.Regatta:
        with self.Session() as s:
            orm = s.get(RegattaORM, regatta.regatta_id)
            if orm is None:
                orm = RegattaORM(regatta_id=regatta.regatta_id)
                s.add(orm)
            M.apply_regatta(orm, regatta)
            s.commit()
        return regatta

    def delete(self, regatta_id: str) -> bool:
        with self.Session() as s:
            orm = s.get(RegattaORM, regatta_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True
