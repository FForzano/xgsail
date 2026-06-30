"""Race-day table."""

from typing import Optional

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class RaceDayORM(Base):
    __tablename__ = "race_days"

    raceday_id: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, default="race_day")
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Soft link to a regatta (loosely coupled — not an enforced FK).
    regatta_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    race_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
