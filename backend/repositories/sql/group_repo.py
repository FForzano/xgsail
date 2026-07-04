"""SQL group repository (+ membership via ``user_groups``). Speculare to
``SqlClubRepo``; membership is soft-deleted (``deleted_at``), not statused."""

import uuid
from typing import Optional

from sqlalchemy import select, update

from ...db.models import GroupORM, UserGroupORM


class SqlGroupRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self) -> "list[GroupORM]":
        with self.Session() as s:
            return list(s.scalars(select(GroupORM)).all())

    def get(self, group_id: uuid.UUID) -> Optional[GroupORM]:
        with self.Session() as s:
            return s.get(GroupORM, group_id)

    def create(self, data: dict) -> GroupORM:
        with self.Session() as s:
            orm = GroupORM(**{k: v for k, v in data.items() if k != "members"})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def add_member(self, group_id: uuid.UUID, *, user_id: uuid.UUID,
                   role: str = "member") -> bool:
        with self.Session() as s:
            exists = s.scalars(
                select(UserGroupORM).where(
                    UserGroupORM.group_id == group_id,
                    UserGroupORM.user_id == user_id,
                )
            ).first()
            if exists is not None:
                return False
            s.add(UserGroupORM(group_id=group_id, user_id=user_id, role=role))
            s.commit()
            return True

    def set_member_role(self, group_id: uuid.UUID, user_id: uuid.UUID, role: str) -> bool:
        with self.Session() as s:
            res = s.execute(
                update(UserGroupORM)
                .where(UserGroupORM.group_id == group_id, UserGroupORM.user_id == user_id)
                .values(role=role)
            )
            s.commit()
            return res.rowcount > 0

    def update(self, group_id: uuid.UUID, changes: dict) -> Optional[GroupORM]:
        allowed = ("name", "description", "profile_image_id", "visibility")
        with self.Session() as s:
            orm = s.get(GroupORM, group_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in allowed:
                    setattr(orm, k, v)
            s.commit()
        return self.get(group_id)

    def soft_delete(self, group_id: uuid.UUID, deleted_by: uuid.UUID) -> bool:
        from datetime import datetime, timezone

        with self.Session() as s:
            orm = s.get(GroupORM, group_id)
            if orm is None:
                return False
            orm.deleted_at = datetime.now(timezone.utc)
            orm.deleted_by = deleted_by
            s.commit()
            return True

    def list_members(self, group_id: uuid.UUID) -> "list[UserGroupORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(UserGroupORM).where(
                    UserGroupORM.group_id == group_id,
                    UserGroupORM.deleted_at.is_(None),
                )
            ).all())

    def remove_member(self, group_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Soft removal (deleted_at), history preserved."""
        from datetime import datetime, timezone

        with self.Session() as s:
            orm = s.scalars(
                select(UserGroupORM).where(
                    UserGroupORM.group_id == group_id,
                    UserGroupORM.user_id == user_id,
                    UserGroupORM.deleted_at.is_(None),
                )
            ).first()
            if orm is None:
                return False
            orm.deleted_at = datetime.now(timezone.utc)
            s.commit()
            return True

    def is_member(self, group_id: uuid.UUID, user_id: uuid.UUID,
                  roles: "Optional[list]" = None) -> bool:
        with self.Session() as s:
            q = select(UserGroupORM).where(
                UserGroupORM.group_id == group_id,
                UserGroupORM.user_id == user_id,
                UserGroupORM.deleted_at.is_(None),
            )
            if roles is not None:
                q = q.where(UserGroupORM.role.in_(roles))
            return s.scalars(q).first() is not None
