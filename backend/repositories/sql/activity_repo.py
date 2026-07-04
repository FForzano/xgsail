"""SQL activity repository: ``activities`` + their per-activity ``marks``.

An activity groups N sessions (boats) over a time window (solo outing, group
training, or a tracked race via ``race_id``). Marks hang off the activity so
trainings get buoys too (see docs/er-project.md).
"""

import uuid
from typing import Optional

from sqlalchemy import select

from ...db.models import ActivityORM, MarkORM

_FIELDS = ("name", "type", "club_id", "race_id", "created_by", "group_id",
           "visibility", "started_at", "ended_at")
_MARK_FIELDS = ("mark_role", "lat", "lng", "set_at")


class SqlActivityRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self, *, club_id: Optional[uuid.UUID] = None,
             group_id: Optional[uuid.UUID] = None,
             race_id: Optional[uuid.UUID] = None,
             type: Optional[str] = None,
             created_by: Optional[uuid.UUID] = None) -> "list[ActivityORM]":
        with self.Session() as s:
            q = select(ActivityORM)
            if club_id is not None:
                q = q.where(ActivityORM.club_id == club_id)
            if group_id is not None:
                q = q.where(ActivityORM.group_id == group_id)
            if race_id is not None:
                q = q.where(ActivityORM.race_id == race_id)
            if type is not None:
                q = q.where(ActivityORM.type == type)
            if created_by is not None:
                q = q.where(ActivityORM.created_by == created_by)
            return list(s.scalars(q).all())

    def get(self, activity_id: uuid.UUID) -> Optional[ActivityORM]:
        with self.Session() as s:
            return s.get(ActivityORM, activity_id)

    def get_by_race(self, race_id: uuid.UUID) -> Optional[ActivityORM]:
        """THE activity tracking a race (first match)."""
        with self.Session() as s:
            return s.scalars(
                select(ActivityORM).where(ActivityORM.race_id == race_id)
            ).first()

    def create(self, data: dict) -> ActivityORM:
        with self.Session() as s:
            orm = ActivityORM(**{k: data.get(k) for k in _FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, activity_id: uuid.UUID, changes: dict) -> Optional[ActivityORM]:
        with self.Session() as s:
            orm = s.get(ActivityORM, activity_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(activity_id)

    def delete(self, activity_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(ActivityORM, activity_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    # --- marks ---

    def list_marks(self, activity_id: uuid.UUID) -> "list[MarkORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(MarkORM).where(MarkORM.activity_id == activity_id)
            ).all())

    def get_mark(self, mark_id: uuid.UUID) -> Optional[MarkORM]:
        with self.Session() as s:
            return s.get(MarkORM, mark_id)

    def add_mark(self, activity_id: uuid.UUID, data: dict) -> MarkORM:
        with self.Session() as s:
            orm = MarkORM(activity_id=activity_id,
                          **{k: data.get(k) for k in _MARK_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_mark(new_id)

    def update_mark(self, mark_id: uuid.UUID, changes: dict) -> Optional[MarkORM]:
        with self.Session() as s:
            orm = s.get(MarkORM, mark_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _MARK_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get_mark(mark_id)

    def delete_mark(self, mark_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(MarkORM, mark_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def replace_marks(self, activity_id: uuid.UUID, marks: "list[dict]") -> "list[MarkORM]":
        """Atomic replace — used by suggest-marks ``apply``."""
        with self.Session() as s:
            for old in s.scalars(select(MarkORM).where(MarkORM.activity_id == activity_id)):
                s.delete(old)
            for m in marks:
                s.add(MarkORM(activity_id=activity_id,
                              **{k: m.get(k) for k in _MARK_FIELDS if k in m}))
            s.commit()
        return self.list_marks(activity_id)
