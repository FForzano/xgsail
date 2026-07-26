"""Device tables: ``device_types`` (catalog) + ``devices`` (registry).

Registration is self-service via claim code (see docs/api-project.md,
"Registrazione device e ingestion dati"): a user generates a ``claim_code``,
the device confirms it with its ``external_id`` and receives a one-time
``device_api_key`` (stored here only as ``api_key_hash``, rotatable without
re-claiming). ``owner_user_id``/``owner_boat_id``/``owner_club_id`` are the
CURRENT assignment (mutually exclusive, all NULL = unclaimed);
``claimed_at``/``claimed_by`` keep the first-association event for audit.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDPKMixin, enum_check

DEVICE_CATEGORIES = ("boat_tracker", "wearable")
DEVICE_STATUSES = ("unclaimed", "claimed", "revoked")


class DeviceTypeORM(UUIDPKMixin, Base):
    __tablename__ = "device_types"
    __table_args__ = (enum_check("category", DEVICE_CATEGORIES),)

    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    # Typical sensor list, informational for the UI only.
    default_sensors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Ingestion adapter id, e.g. "sailframes_e1_csv", "garmin_fit", "generic_gpx".
    parser_key: Mapped[str] = mapped_column(String, nullable=False)


class DeviceORM(UUIDPKMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (
        enum_check("status", DEVICE_STATUSES),
        CheckConstraint(
            "num_nonnulls(owner_user_id, owner_boat_id, owner_club_id) <= 1",
            name="owner_at_most_one",
        ),
    )
    __wire_exclude__ = ("api_key_hash", "claim_code")

    device_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_types.id", ondelete="RESTRICT"), nullable=False
    )
    # Hardware serial / BLE UUID / MAC — set by the device at claim confirm.
    external_id: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    owner_boat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("boats.id", ondelete="SET NULL"), nullable=True
    )
    owner_club_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True
    )
    nickname: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="unclaimed")
    claim_code: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    claim_code_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Hash of the device_api_key issued at claim; rotatable via rotate-key.
    api_key_hash: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    # Set when the owner "forgets" an already-revoked device: hides it from
    # list views without deleting the row (ingest history RESTRICT-references
    # devices.id, so a hard delete isn't generally possible once used).
    hidden_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
