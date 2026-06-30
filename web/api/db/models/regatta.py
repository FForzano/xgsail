"""Regatta table."""

from typing import Any, Optional

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class RegattaORM(Base):
    __tablename__ = "regattas"

    regatta_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    venue: Mapped[str] = mapped_column(String, default="")
    boat_class: Mapped[Any] = mapped_column(JSON, nullable=True)
    start_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rating_system: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_sequence_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Soft list of linked race ids (maintained by the endpoints, mirrors domain).
    race_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
