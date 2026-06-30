"""Session (manifest metadata) table.

Only manifest-level metadata; the bulk sensor payloads always stay in the blob
store. Unique per (device_id, date) to mirror the object layout.
"""

from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

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
