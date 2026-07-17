"""SQL post repository — feed posts owned by a club or a group. No soft
delete (unlike clubs/regattas): a post carries no downstream history to
preserve, so removal is a hard delete."""

import uuid
from typing import Optional

from sqlalchemy import delete, select

from ...db.models import PostORM


class SqlPostRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list_for_owner(self, owner_type: str, owner_id: uuid.UUID) -> "list[PostORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(PostORM)
                .where(PostORM.owner_type == owner_type, PostORM.owner_id == owner_id)
                .order_by(PostORM.created_at.desc())
            ).all())

    def get(self, post_id: uuid.UUID) -> Optional[PostORM]:
        with self.Session() as s:
            return s.get(PostORM, post_id)

    def create(self, data: dict) -> PostORM:
        with self.Session() as s:
            orm = PostORM(**data)
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def delete(self, post_id: uuid.UUID) -> bool:
        with self.Session() as s:
            res = s.execute(delete(PostORM).where(PostORM.id == post_id))
            s.commit()
            return res.rowcount > 0
