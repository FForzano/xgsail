"""Race-structure tables: ``regattas`` -> ``race_days`` -> ``races`` +
per-boat ``results`` and ``regatta_entries``.

A race day may be "free" (``regatta_id`` NULL, e.g. a club training day with
timed starts). Results are one row per boat per race and can exist without a
GPS trace (``session_id`` nullable). Marks are NOT here — they hang off
``activities`` (see ``activity.py``) so trainings can have buoys too.

``regatta_entries`` is the start list, and is deliberately NOT the same thing
as ``results``: an entry says "this boat is expected at this event" and must
exist *before* the racing, whereas a result carries scoring
(``position``/``score``/``status``) and would pollute the standings if
pre-created. It is also per-regatta, not per-race — a boat enters the event
once and sails all of its races.

An entry's ``boat_id`` is nullable: an organizer can pre-populate a start
list with boats that don't have an XGSail account/boat record yet (paper
entries), captured instead as ``boat_name``/``sail_number``. Such a manual
entry can later be linked to a real boat (``link_entry``), which clears the
manual fields. Uniqueness is therefore two partial indexes rather than one
plain constraint: ``(regatta_id, boat_id)`` where ``boat_id`` is set, and
``(regatta_id, boat_name_normalized)`` where it isn't — plus a CHECK that at
least one of ``boat_id``/``boat_name`` is present.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String,
    Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, UUIDPKMixin, enum_check

SCORING_SYSTEMS = ("low_point", "bonus_point", "custom")
REGATTA_STATUSES = ("scheduled", "active", "completed")
RACE_STATUSES = ("scheduled", "started", "finished", "abandoned")
RESULT_STATUSES = ("finished", "dnf", "dns", "dsq", "ocs", "ret")
# How a boat got onto the start list: added by the organizer, or self-joined
# with the regatta's share code.
ENTRY_SOURCES = ("organizer", "code")


class RegattaORM(UUIDPKMixin, Base):
    __tablename__ = "regattas"
    __table_args__ = (
        enum_check("scoring_system", SCORING_SYSTEMS),
        enum_check("status", REGATTA_STATUSES),
        UniqueConstraint("join_code"),
    )
    # Regattas are publicly readable, so the share code must never ride along
    # on the regular payload — it is served only by the manage-gated endpoint.
    __wire_exclude__ = ("join_code",)

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
    # Share code letting a sailor put their own boat on the start list without
    # being a club member. NULL = no code / revoked; regenerating simply
    # overwrites it, which invalidates any link already handed out.
    join_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class RegattaEntryORM(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "regatta_entries"
    __table_args__ = (
        # Partial rather than plain unique: a linked entry is unique per
        # boat, a manual (unlinked) one is unique per normalized name — the
        # two populations never collide with each other on the same index.
        Index(
            "uq_regatta_entries_regatta_boat",
            "regatta_id", "boat_id",
            unique=True,
            postgresql_where=text("boat_id IS NOT NULL"),
            sqlite_where=text("boat_id IS NOT NULL"),
        ),
        Index(
            "uq_regatta_entries_regatta_manual_name",
            "regatta_id", "boat_name_normalized",
            unique=True,
            postgresql_where=text("boat_id IS NULL"),
            sqlite_where=text("boat_id IS NULL"),
        ),
        CheckConstraint(
            "boat_id IS NOT NULL OR boat_name IS NOT NULL",
            name="boat_id_or_boat_name",
        ),
        enum_check("source", ENTRY_SOURCES),
    )

    regatta_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("regattas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable: a manual (paper) entry has no boat record yet — see module
    # docstring. RESTRICT mirrors ``results``: never silently drop a start
    # list by deleting a boat once one is linked.
    boat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("boats.id", ondelete="RESTRICT"), nullable=True
    )
    # Manual-entry fields, populated only while boat_id is NULL; cleared by
    # link_entry() once the entry is matched to a real boat.
    boat_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sail_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Bookkeeping only (not part of the API payload): lower/trimmed
    # "name|sail_number" used by the partial unique index above and by
    # add_entry's idempotency check. Never read directly by callers.
    boat_name_normalized: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="organizer")
    # Who put the boat on the list — the organizer, or the sailor themselves.
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __wire_exclude__ = ("boat_name_normalized",)


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
