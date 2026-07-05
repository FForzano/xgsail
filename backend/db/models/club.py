"""Clubs and club membership (``clubs``, ``user_clubs``).

Membership (``user_clubs``) is plain visibility/affiliation — independent of
the RBAC roles: a scoped ``club_admin``/``race_officer`` grant lives in
``user_roles.scope_club_id``. Clubs are never hard-deleted; they are
deactivated via ``is_active`` to preserve history (regattas, members, boats).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin, enum_check

# invited = manager invited the user (user accepts); requested = user asked to
# join (manager approves). Both are pending, but who may activate them differs.
USER_CLUB_STATUSES = ("invited", "requested", "active", "deleted")


class ClubORM(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "clubs"
    __wire_children__ = {"members": "members"}

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_line_1: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address_line_2: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    state_province: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # free format
    country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)  # ISO 3166-1 alpha-2
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    founded_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    logo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    members: Mapped[list["UserClubORM"]] = relationship(
        back_populates="club", cascade="all, delete-orphan", lazy="selectin"
    )


class UserClubORM(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "user_clubs"
    __table_args__ = (
        UniqueConstraint("user_id", "club_id"),
        enum_check("status", USER_CLUB_STATUSES),
    )
    __wire_exclude__ = ("id", "club_id")

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="invited")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    club: Mapped["ClubORM"] = relationship(back_populates="members")
