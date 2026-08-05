"""Boat tables: ``boat_classes``, ``boats``, ``user_boats``, ``boat_photos``,
``boat_notes``.

``user_boats`` is the per-resource ownership layer (owner|admin|visitor — no
centralized RBAC check, the relationship itself grants access) plus the
default sailing role used to prefill ``session_crew``. Documents (cert/mbsa)
point at ``files``; photos at ``images`` via ``boat_photos``; free-text
rig-tuning entries live in ``boat_notes``, ordered by an explicit ``position``.
"""

import uuid
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin, enum_check

USER_BOAT_ROLES = ("owner", "admin", "visitor")
SAILING_ROLES = ("skipper", "crew")
HULL_TYPES = ("monohull", "multihull")
# Mirror the RYA Portsmouth Yardstick list's "Rig" (S/U) and "Spinnaker"
# (0/A/C) columns so a class transcribed from the published PDF maps 1:1.
RIG_TYPES = ("sloop", "una")
SPINNAKER_TYPES = ("none", "asymmetric", "symmetric")


class BoatClassORM(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "boat_classes"
    __table_args__ = (
        enum_check("hull_type", HULL_TYPES),
        enum_check("rig_type", RIG_TYPES),
        enum_check("spinnaker_type", SPINNAKER_TYPES),
        UniqueConstraint("rya_class_id"),
    )

    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    # Class-specific technical details (all optional — filled in by the
    # superadmin catalog editor).
    loa_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beam_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sail_area_sqm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    crew_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hull_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # RYA PY list fields — rig/spinnaker/number map to the official
    # Rig/Spinnaker/Number columns; rya_class_id to RYA Class ID (reference
    # only, no import/sync against the published list).
    rig_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    spinnaker_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    py_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rya_class_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class BoatORM(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "boats"
    __wire_children__ = {"members": "members"}

    name: Mapped[str] = mapped_column(String, nullable=False)
    boat_class_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("boat_classes.id", ondelete="SET NULL"), nullable=True
    )
    sail_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    loa_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cert_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    mbsa_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    # Optional: the club where the boat is stationed.
    club_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True
    )

    members: Mapped[list["UserBoatORM"]] = relationship(
        back_populates="boat", cascade="all, delete-orphan", lazy="selectin"
    )


class UserBoatORM(UUIDPKMixin, Base):
    """Many-to-many user<->boat: a user can have several boats and vice versa."""

    __tablename__ = "user_boats"
    __table_args__ = (
        UniqueConstraint("user_id", "boat_id"),
        enum_check("role", USER_BOAT_ROLES),
        enum_check("default_sailing_role", SAILING_ROLES),
    )
    __wire_exclude__ = ("id", "boat_id")

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    boat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("boats.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String, nullable=False, default="visitor")
    # Default only — the actual per-outing role is session_crew.sailing_role.
    default_sailing_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    boat: Mapped["BoatORM"] = relationship(back_populates="members")


class BoatPhotoORM(UUIDPKMixin, Base):
    __tablename__ = "boat_photos"
    __table_args__ = (UniqueConstraint("boat_id", "image_id"),)

    boat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("boats.id", ondelete="CASCADE"))
    image_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"))


class BoatNoteORM(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "boat_notes"

    boat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("boats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # No uniqueness on (boat_id, position): enforcing it would turn every
    # reorder into a multi-statement dance around collisions for no benefit.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
