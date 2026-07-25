"""SQL note-template repository — per-user free-text snippets for prefilling
session crew notes. Always scoped to the owner; no soft delete (no
downstream history to preserve)."""

import uuid
from typing import Optional

from sqlalchemy import delete, select

from ...db.models import NoteTemplateORM

_FIELDS = ("name", "body", "updated_at")


class SqlNoteTemplateRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list_for_user(self, user_id: uuid.UUID) -> "list[NoteTemplateORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(NoteTemplateORM)
                .where(NoteTemplateORM.user_id == user_id)
                .order_by(NoteTemplateORM.name)
            ).all())

    def get(self, template_id: uuid.UUID) -> Optional[NoteTemplateORM]:
        with self.Session() as s:
            return s.get(NoteTemplateORM, template_id)

    def create(self, user_id: uuid.UUID, name: str, body: str) -> NoteTemplateORM:
        with self.Session() as s:
            orm = NoteTemplateORM(user_id=user_id, name=name, body=body)
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, template_id: uuid.UUID, changes: dict) -> Optional[NoteTemplateORM]:
        with self.Session() as s:
            orm = s.get(NoteTemplateORM, template_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(template_id)

    def delete(self, template_id: uuid.UUID) -> bool:
        with self.Session() as s:
            res = s.execute(delete(NoteTemplateORM).where(NoteTemplateORM.id == template_id))
            s.commit()
            return res.rowcount > 0
