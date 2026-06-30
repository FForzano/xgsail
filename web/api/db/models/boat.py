"""Boat catalog table."""

from typing import Optional

from sqlalchemy import JSON, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class BoatORM(Base):
    __tablename__ = "boats"

    boat_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, default="")
    type: Mapped[str] = mapped_column(String, default="")
    sail_number: Mapped[str] = mapped_column(String, default="")
    club: Mapped[str] = mapped_column(String, default="")
    loa_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    skippers: Mapped[list] = mapped_column(JSON, default=list)
    photos: Mapped[dict] = mapped_column(JSON, default=dict)
    cert_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mbsa_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    links: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(String, default="")
    polar: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
