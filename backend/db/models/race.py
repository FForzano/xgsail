"""Race-structure tables: ``regattas`` -> ``race_days`` -> ``races`` +
per-boat ``results``.

A race day may be "free" (``regatta_id`` NULL, e.g. a club training day with
timed starts). Results are one row per boat per race and can exist without a
GPS trace (``session_id`` nullable). Marks are NOT here — they hang off
``activities`` (see ``activity.py``) so trainings can have buoys too.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDPKMixin, enum_check

SCORING_SYSTEMS = ("low_point", "bonus_point", "custom")
REGATTA_STATUSES = ("scheduled", "active", "completed")
RACE_STATUSES = ("scheduled", "started", "finished", "abandoned")
RESULT_STATUSES = ("finished", "dnf", "dns", "dsq", "ocs", "ret")


class RegattaORM(UUIDPKMixin, Base):
    __tablename__ = "regattas"
    __table_args__ = (
        enum_check("scoring_system", SCORING_SYSTEMS),
        enum_check("status", REGATTA_STATUSES),
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    # RESTRICT: clubs are deactivated (is_active), never hard-deleted.
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clubs.id", ondelete="RESTRICT"), nullable=False
    )
    # Optional main class/fleet (a regatta is typically mono-class).
    class_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("boat_classes.id", ondelete="SET NULL"), nullable=True
    )
    scoring_system: Mapped[str] = mapped_column(String, nullable=False, default="low_point")
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="scheduled")


class RaceDayORM(UUIDPKMixin, Base):
    __tablename__ = "race_days"

    # NULL = "free" race day not tied to a regatta.
    regatta_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("regattas.id", ondelete="CASCADE"), nullable=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RaceORM(UUIDPKMixin, Base):
    __tablename__ = "races"
    __table_args__ = (
        UniqueConstraint("race_day_id", "race_number"),
        enum_check("status", RACE_STATUSES),
    )

    race_day_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("race_days.id", ondelete="CASCADE"), nullable=False
    )
    race_number: Mapped[int] = mapped_column(Integer, nullable=False)  # race 1, 2, 3 of the day
    status: Mapped[str] = mapped_column(String, nullable=False, default="scheduled")
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ResultORM(UUIDPKMixin, Base):
    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint("race_id", "boat_id"),
        enum_check("status", RESULT_STATUSES),
    )

    race_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("races.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT: never silently lose results by deleting a boat.
    boat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("boats.id", ondelete="RESTRICT"), nullable=False
    )
    # NULL: result can be entered without a GPS trace.
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    finish_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # seconds
    corrected_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # seconds
    position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # redress can be fractional
    status: Mapped[str] = mapped_column(String, nullable=False, default="finished")
