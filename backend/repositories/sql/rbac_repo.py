"""SQL RBAC repository: role/permission catalog reads + user_role grants.

Used by club creation (grant scoped ``club_admin`` to the creator) and the
user-roles admin API. Permission *checking* stays in ``backend/auth``.
"""

import uuid
from typing import Optional

from sqlalchemy import select

from ...db.models import PermissionORM, RoleORM, UserRoleORM


class SqlRbacRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list_roles(self) -> "list[RoleORM]":
        with self.Session() as s:
            return list(s.scalars(select(RoleORM)).all())

    def get_role(self, role_id: uuid.UUID) -> Optional[RoleORM]:
        with self.Session() as s:
            return s.get(RoleORM, role_id)

    def get_role_by_name(self, name: str) -> Optional[RoleORM]:
        with self.Session() as s:
            return s.scalars(select(RoleORM).where(RoleORM.name == name)).first()

    def list_permissions(self) -> "list[PermissionORM]":
        with self.Session() as s:
            return list(s.scalars(select(PermissionORM)).all())

    def grant_role(self, user_id: uuid.UUID, role_id: uuid.UUID,
                   scope_club_id: Optional[uuid.UUID] = None) -> UserRoleORM:
        """Idempotent grant — returns the existing row if already granted."""
        with self.Session() as s:
            q = select(UserRoleORM).where(
                UserRoleORM.user_id == user_id,
                UserRoleORM.role_id == role_id,
                UserRoleORM.scope_club_id == scope_club_id if scope_club_id is not None
                else UserRoleORM.scope_club_id.is_(None),
            )
            existing = s.scalars(q).first()
            if existing is not None:
                return existing
            orm = UserRoleORM(user_id=user_id, role_id=role_id, scope_club_id=scope_club_id)
            s.add(orm)
            s.commit()
            s.refresh(orm)
            s.expunge(orm)
            return orm

    def get_user_role(self, user_role_id: uuid.UUID) -> Optional[UserRoleORM]:
        with self.Session() as s:
            return s.get(UserRoleORM, user_role_id)

    def revoke_user_role(self, user_role_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(UserRoleORM, user_role_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def list_user_roles(self, *, user_id: Optional[uuid.UUID] = None,
                        scope_club_id: Optional[uuid.UUID] = None) -> "list[UserRoleORM]":
        with self.Session() as s:
            q = select(UserRoleORM)
            if user_id is not None:
                q = q.where(UserRoleORM.user_id == user_id)
            if scope_club_id is not None:
                q = q.where(UserRoleORM.scope_club_id == scope_club_id)
            return list(s.scalars(q).all())
