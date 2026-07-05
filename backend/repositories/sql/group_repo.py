"""SQL group repository (+ membership via ``user_groups``). Speculare to
``SqlClubRepo``: membership carries ``status`` (invited|active) for invites;
removal is soft (``deleted_at``)."""

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
                   role: str = "member", status: str = "active") -> bool:
        with self.Session() as s:
            exists = s.scalars(
                select(UserGroupORM).where(
                    UserGroupORM.group_id == group_id,
                    UserGroupORM.user_id == user_id,
                )
            ).first()
            if exists is not None:
                # Re-inviting someone who previously left reactivates the row.
                if exists.deleted_at is not None:
                    exists.deleted_at = None
                    exists.role = role
                    exists.status = status
                    s.commit()
                    return True
                return False
            s.add(UserGroupORM(group_id=group_id, user_id=user_id, role=role, status=status))
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

    def set_member_status(self, group_id: uuid.UUID, user_id: uuid.UUID, status: str) -> bool:
        with self.Session() as s:
            res = s.execute(
                update(UserGroupORM)
                .where(
                    UserGroupORM.group_id == group_id,
                    UserGroupORM.user_id == user_id,
                    UserGroupORM.deleted_at.is_(None),
                )
                .values(status=status)
            )
            s.commit()
            return res.rowcount > 0

    def get_member(self, group_id: uuid.UUID, user_id: uuid.UUID) -> Optional[UserGroupORM]:
        with self.Session() as s:
            return s.scalars(
                select(UserGroupORM).where(
                    UserGroupORM.group_id == group_id,
                    UserGroupORM.user_id == user_id,
                    UserGroupORM.deleted_at.is_(None),
                )
            ).first()

    def list_memberships_for_user(self, user_id: uuid.UUID) -> "list[dict]":
        """My group memberships (incl. pending invites), with the group name —
        powers ``GET /api/users/me/memberships``."""
        with self.Session() as s:
            rows = s.execute(
                select(UserGroupORM, GroupORM.name)
                .join(GroupORM, GroupORM.id == UserGroupORM.group_id)
                .where(
                    UserGroupORM.user_id == user_id,
                    UserGroupORM.deleted_at.is_(None),
                    GroupORM.deleted_at.is_(None),
                )
            ).all()
            return [
                {"group_id": m.group_id, "name": name, "role": m.role,
                 "status": m.status, "created_at": m.created_at}
                for m, name in rows
            ]

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
        """Active members only — an ``invited`` row grants no access yet."""
        with self.Session() as s:
            q = select(UserGroupORM).where(
                UserGroupORM.group_id == group_id,
                UserGroupORM.user_id == user_id,
                UserGroupORM.status == "active",
                UserGroupORM.deleted_at.is_(None),
            )
            if roles is not None:
                q = q.where(UserGroupORM.role.in_(roles))
            return s.scalars(q).first() is not None
