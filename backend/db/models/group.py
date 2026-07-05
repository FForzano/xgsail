"""Groups and group membership (``groups``, ``user_groups``).

Informal training/social circles, unlike clubs (institutional). ``visibility``
public = discoverable and readable by anyone, private = members only; join is
invite-only in both cases. Ownership is per-resource (``user_groups.role``),
not RBAC.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, CreatedAtMixin, UUIDPKMixin, enum_check

GROUP_VISIBILITIES = ("public", "private")
USER_GROUP_ROLES = ("owner", "admin", "member")
# invited = manager invited the user (user accepts); requested = user asked to
# join a public group (manager approves). Mirrors user_clubs.status.
USER_GROUP_STATUSES = ("invited", "requested", "active")


class GroupORM(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "groups"
    __table_args__ = (enum_check("visibility", GROUP_VISIBILITIES),)
    __wire_children__ = {"members": "members"}

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile_image_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="private")
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    members: Mapped[list["UserGroupORM"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", lazy="selectin"
    )


class UserGroupORM(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "user_groups"
    __table_args__ = (
        UniqueConstraint("user_id", "group_id"),
        enum_check("role", USER_GROUP_ROLES),
        enum_check("status", USER_GROUP_STATUSES),
    )
    __wire_exclude__ = ("id", "group_id")

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")
    # Removal stays deleted_at, so no "deleted" value here (unlike user_clubs).
    status: Mapped[str] = mapped_column(String, nullable=False, default="active",
                                        server_default="active")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    group: Mapped["GroupORM"] = relationship(back_populates="members")
