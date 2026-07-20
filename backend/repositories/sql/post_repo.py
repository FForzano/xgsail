"""SQL post repository — feed posts owned by a club or a group. No soft
delete (unlike clubs/regattas): a post carries no downstream history to
preserve, so removal is a hard delete."""

import uuid
from typing import Optional

from sqlalchemy import delete, select

from ...db.models import PostImageORM, PostORM

_POST_FIELDS = ("body", "updated_at")


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

    def update(self, post_id: uuid.UUID, changes: dict) -> Optional[PostORM]:
        with self.Session() as s:
            orm = s.get(PostORM, post_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _POST_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(post_id)

    def delete(self, post_id: uuid.UUID) -> bool:
        with self.Session() as s:
            res = s.execute(delete(PostORM).where(PostORM.id == post_id))
            s.commit()
            return res.rowcount > 0

    # --- post_images links ---

    def list_images(self, post_id: uuid.UUID) -> "list[PostImageORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(PostImageORM).where(PostImageORM.post_id == post_id)
            ).all())

    def add_image(self, post_id: uuid.UUID, image_id: uuid.UUID) -> PostImageORM:
        with self.Session() as s:
            orm = PostImageORM(post_id=post_id, image_id=image_id)
            s.add(orm)
            s.commit()
            s.refresh(orm)
            s.expunge(orm)
            return orm
