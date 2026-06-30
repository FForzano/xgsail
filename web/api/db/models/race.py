"""Race aggregate tables: races + child marks/race_boats + 1:1 race_results.

``regatta_id`` / ``raceday_id`` are soft links (plain columns, not enforced
FKs) because the UI links races to series/days loosely; the marks, race_boats
and result rows are owned children with cascade delete.
"""

from typing import Optional

from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class MarkORM(Base):
    __tablename__ = "marks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[str] = mapped_column(ForeignKey("races.race_id", ondelete="CASCADE"))
    mark_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String, default="")
    mark_type: Mapped[str] = mapped_column(String, default="custom")
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)

    race: Mapped["RaceORM"] = relationship(back_populates="marks")


class RaceBoatORM(Base):
    __tablename__ = "race_boats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[str] = mapped_column(ForeignKey("races.race_id", ondelete="CASCADE"))
    device_id: Mapped[str] = mapped_column(String)
    boat_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    boat_name: Mapped[str] = mapped_column(String, default="")
    sail_number: Mapped[str] = mapped_column(String, default="")
    session_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    gpx_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    polar: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    race: Mapped["RaceORM"] = relationship(back_populates="boats")


class RaceResultORM(Base):
    __tablename__ = "race_results"

    race_id: Mapped[str] = mapped_column(
        ForeignKey("races.race_id", ondelete="CASCADE"), primary_key=True
    )
    finish_order: Mapped[list] = mapped_column(JSON, default=list)
    boat_results: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    race: Mapped["RaceORM"] = relationship(back_populates="result")


class RaceORM(Base):
    __tablename__ = "races"

    race_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[str] = mapped_column(String, nullable=False)
    end_time: Mapped[str] = mapped_column(String, nullable=False)
    regatta_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raceday_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_line: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    finish_line: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    course: Mapped[list] = mapped_column(JSON, default=list)
    finish_order: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    marks: Mapped[list[MarkORM]] = relationship(
        back_populates="race", cascade="all, delete-orphan"
    )
    boats: Mapped[list[RaceBoatORM]] = relationship(
        back_populates="race", cascade="all, delete-orphan"
    )
    result: Mapped[Optional[RaceResultORM]] = relationship(
        back_populates="race", cascade="all, delete-orphan", uselist=False
    )
