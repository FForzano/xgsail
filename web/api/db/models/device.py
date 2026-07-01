"""Device tables: tracker registry (``devices``) + attribution windows
(``device_assignments``).

``device_id`` is the natural primary key (the string the firmware uploads
under, ``raw/{device_id}/…``). Assignment windows attribute a club/RC device to
a boat for a bounded period; boat-private devices use ``default_boat_id``
instead. See ``domain/device.py`` for the resolution order.
"""

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class DeviceORM(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    device_type: Mapped[str] = mapped_column(String, default="sailframes_e")
    default_boat_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("boats.boat_id", ondelete="SET NULL"), nullable=True
    )
    owner_type: Mapped[str] = mapped_column(String, default="user")  # user | club
    registered_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    owned_by_club_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, default="active")  # active | revoked
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_seen_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    assignments: Mapped[list["DeviceAssignmentORM"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class DeviceAssignmentORM(Base):
    """A bounded [valid_from, valid_to) attribution of a device to a boat.
    Windows for one device must not overlap (enforced in the repo, 409)."""

    __tablename__ = "device_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.device_id", ondelete="CASCADE"), index=True
    )
    boat_id: Mapped[str] = mapped_column(String, nullable=False)
    regatta_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    race_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    valid_from: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    valid_to: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    device: Mapped["DeviceORM"] = relationship(back_populates="assignments")
