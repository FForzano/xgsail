"""Session (manifest metadata) table.

Only manifest-level metadata; the bulk sensor payloads always stay in the blob
store. Unique per (device_id, date) to mirror the object layout.

⚠️ ``date`` is a **folder slug** (``YYYYMMDD`` or ``session_NNN``), not a
calendar date — it is the per-outing identifier, half of the uniqueness key. Do
not compute on it. Phase 5 adds the privacy/attribution columns + the
``session_crew`` table (the actual crew of the outing, distinct from a boat's
standing ``boat_members``).
"""

from typing import Any, Optional

from sqlalchemy import (
    ForeignKey,
    Integer,
    JSON,
    Boolean,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class SessionORM(Base):
    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("device_id", "date", name="uq_session_device_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_time: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    end_time: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    boat: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sensors: Mapped[Any] = mapped_column(JSON, nullable=True)
    has_video: Mapped[bool] = mapped_column(Boolean, default=False)
    has_analysis: Mapped[bool] = mapped_column(Boolean, default=False)
    trim: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # --- Phase 5: privacy + attribution ---
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    boat_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    visibility: Mapped[str] = mapped_column(String, default="private")
    club_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True
    )
    group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    regatta_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    race_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    crew: Mapped[list["SessionCrewORM"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SessionCrewORM(Base):
    """A crew slot on one session. Exactly one of ``user_id`` / ``guest_name``
    is set (a registered user, or a guest without an account)."""

    __tablename__ = "session_crew"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    guest_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    boat_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    session: Mapped["SessionORM"] = relationship(back_populates="crew")
