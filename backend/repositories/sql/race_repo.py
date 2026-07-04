"""SQL race-structure repositories: regattas -> race_days -> races (+ results).

Results are per-boat rows on ``SqlRaceRepo`` (unique per race+boat, upsert).
``club_id_for_race``/``club_id_for_raceday`` resolve the RBAC scope for
``require_permission(key, club_id=...)`` — ``None`` for free race days
(``regatta_id`` NULL), which therefore require a global grant/superadmin.
"""

import uuid
from datetime import date as date_t
from typing import Optional

from sqlalchemy import select

from ...db.models import RaceDayORM, RaceORM, RegattaORM, ResultORM

_REGATTA_FIELDS = ("name", "description", "club_id", "class_id",
                   "scoring_system", "start_date", "end_date", "status")
_RACEDAY_FIELDS = ("regatta_id", "date", "notes")
_RACE_FIELDS = ("race_day_id", "race_number", "status", "start_time")
_RESULT_FIELDS = ("session_id", "finish_time", "elapsed_time", "corrected_time",
                  "position", "score", "status")


class SqlRegattaRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self, *, club_id: Optional[uuid.UUID] = None,
             status: Optional[str] = None) -> "list[RegattaORM]":
        with self.Session() as s:
            q = select(RegattaORM)
            if club_id is not None:
                q = q.where(RegattaORM.club_id == club_id)
            if status is not None:
                q = q.where(RegattaORM.status == status)
            return list(s.scalars(q).all())

    def get(self, regatta_id: uuid.UUID) -> Optional[RegattaORM]:
        with self.Session() as s:
            return s.get(RegattaORM, regatta_id)

    def create(self, data: dict) -> RegattaORM:
        with self.Session() as s:
            orm = RegattaORM(**{k: data.get(k) for k in _REGATTA_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, regatta_id: uuid.UUID, changes: dict) -> Optional[RegattaORM]:
        with self.Session() as s:
            orm = s.get(RegattaORM, regatta_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _REGATTA_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(regatta_id)

    def delete(self, regatta_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(RegattaORM, regatta_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True


class SqlRaceDayRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self, *, regatta_id: Optional[uuid.UUID] = None,
             date: Optional[date_t] = None) -> "list[RaceDayORM]":
        with self.Session() as s:
            q = select(RaceDayORM)
            if regatta_id is not None:
                q = q.where(RaceDayORM.regatta_id == regatta_id)
            if date is not None:
                q = q.where(RaceDayORM.date == date)
            return list(s.scalars(q).all())

    def get(self, raceday_id: uuid.UUID) -> Optional[RaceDayORM]:
        with self.Session() as s:
            return s.get(RaceDayORM, raceday_id)

    def create(self, data: dict) -> RaceDayORM:
        with self.Session() as s:
            orm = RaceDayORM(**{k: data.get(k) for k in _RACEDAY_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, raceday_id: uuid.UUID, changes: dict) -> Optional[RaceDayORM]:
        with self.Session() as s:
            orm = s.get(RaceDayORM, raceday_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _RACEDAY_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(raceday_id)

    def delete(self, raceday_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(RaceDayORM, raceday_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def club_id_for_raceday(self, raceday_id: uuid.UUID) -> Optional[uuid.UUID]:
        with self.Session() as s:
            rd = s.get(RaceDayORM, raceday_id)
            if rd is None or rd.regatta_id is None:
                return None
            regatta = s.get(RegattaORM, rd.regatta_id)
            return regatta.club_id if regatta else None


class SqlRaceRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self, *, race_day_id: Optional[uuid.UUID] = None) -> "list[RaceORM]":
        with self.Session() as s:
            q = select(RaceORM)
            if race_day_id is not None:
                q = q.where(RaceORM.race_day_id == race_day_id)
            return list(s.scalars(q).all())

    def get(self, race_id: uuid.UUID) -> Optional[RaceORM]:
        with self.Session() as s:
            return s.get(RaceORM, race_id)

    def create(self, data: dict) -> RaceORM:
        with self.Session() as s:
            orm = RaceORM(**{k: data.get(k) for k in _RACE_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, race_id: uuid.UUID, changes: dict) -> Optional[RaceORM]:
        with self.Session() as s:
            orm = s.get(RaceORM, race_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _RACE_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(race_id)

    def delete(self, race_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(RaceORM, race_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def club_id_for_race(self, race_id: uuid.UUID) -> Optional[uuid.UUID]:
        with self.Session() as s:
            race = s.get(RaceORM, race_id)
            if race is None:
                return None
            rd = s.get(RaceDayORM, race.race_day_id)
            if rd is None or rd.regatta_id is None:
                return None
            regatta = s.get(RegattaORM, rd.regatta_id)
            return regatta.club_id if regatta else None

    # --- results (one row per race+boat) ---

    def list_results(self, race_id: uuid.UUID) -> "list[ResultORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(ResultORM).where(ResultORM.race_id == race_id)
            ).all())

    def get_result(self, result_id: uuid.UUID) -> Optional[ResultORM]:
        with self.Session() as s:
            return s.get(ResultORM, result_id)

    def upsert_result(self, race_id: uuid.UUID, boat_id: uuid.UUID,
                      data: dict) -> ResultORM:
        with self.Session() as s:
            orm = s.scalars(
                select(ResultORM).where(
                    ResultORM.race_id == race_id, ResultORM.boat_id == boat_id
                )
            ).first()
            if orm is None:
                orm = ResultORM(race_id=race_id, boat_id=boat_id)
                s.add(orm)
            for k, v in data.items():
                if k in _RESULT_FIELDS:
                    setattr(orm, k, v)
            s.commit()
            new_id = orm.id
        return self.get_result(new_id)

    def delete_result(self, race_id: uuid.UUID, boat_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.scalars(
                select(ResultORM).where(
                    ResultORM.race_id == race_id, ResultORM.boat_id == boat_id
                )
            ).first()
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True
