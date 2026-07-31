"""Activities (``activities``) and their per-activity buoys (``marks``).

An activity groups N sessions (boats) over the same time window regardless of
whether it is a regatta: solo outing = one session; group training = N
sessions, type=training, no race; tracked race = type=race + ``race_id``.

Marks are a per-activity instance (GPS-placed each day), not a reusable course
template — parented to ``activity_id`` (not ``race_id``) so a training without
a regatta can have its buoys too.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDPKMixin, enum_check

ACTIVITY_TYPES = ("race", "training", "solo")
ACTIVITY_VISIBILITIES = ("public", "club", "group", "private")
# "planned" = announced ahead of time (a club outing, or a scheduled race —
# see routers/races.py, which creates a race's activity up front so entered
# sailors can pick it before the start); "completed" = has (or once had)
# recorded data — the default, so every activity created alongside a session
# (the common case) needs no explicit status.
#
# Attaching a session does NOT flip planned -> completed: several boats attach
# to the same event over time, so upcoming vs. past is decided by
# ``started_at`` alone (see routers/sessions.py::attach_to_activity).
ACTIVITY_STATUSES = ("planned", "completed")
MARK_ROLES = (
    "pin",
    "rc",
    "windward",
    "leeward",
    "gate_port",
    "gate_stbd",
    "offset",
    "drill",
    # Finish line — mirrors pin/rc (its own pair of marks) rather than
    # reusing them, since a course can finish on a different line than it
    # started (see frontend's "same as start" convenience autofill, which
    # copies pin/rc's coordinates into these when the two lines coincide).
    "finish_pin",
    "finish_rc",
)


class ActivityORM(UUIDPKMixin, Base):
    __tablename__ = "activities"
    __table_args__ = (
        enum_check("type", ACTIVITY_TYPES),
        enum_check("visibility", ACTIVITY_VISIBILITIES),
        enum_check("status", ACTIVITY_STATUSES),
    )

    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    club_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True
    )
    race_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("races.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="private")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Overlay PNG (one track per session, different color each) rendered by
    # the worker whenever a session in this activity finishes processing —
    # shown as the card thumbnail in the unified Activities list.
    thumbnail_image_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )


class MarkORM(UUIDPKMixin, Base):
    __tablename__ = "marks"
    __table_args__ = (enum_check("mark_role", MARK_ROLES),)

    activity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mark_role: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    set_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
