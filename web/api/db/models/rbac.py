"""RBAC tables: users, clubs, roles, permissions, and the join tables.

Full role-based access control: permissions are assigned to roles
(``role_permissions``), roles are granted to users optionally scoped to a club
(``user_roles.scope_club_id`` NULL = global). See ``web/api/auth`` for how
these are evaluated and seeded.
"""

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    roles: Mapped[list["UserRoleORM"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ClubORM(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class RoleORM(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    permissions: Mapped[list["RolePermissionORM"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class PermissionORM(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class RolePermissionORM(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"))

    role: Mapped["RoleORM"] = relationship(back_populates="permissions")


class UserRoleORM(Base):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    # NULL scope = global grant; otherwise the role applies within this club.
    scope_club_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True
    )

    user: Mapped["UserORM"] = relationship(back_populates="roles")
