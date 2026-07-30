"""Ingestion tables: ``imports``, ``session_uploads``, ``session_streams``.

A session can have N ``session_uploads`` (one per contributing device or
manual import), each with its own raw bundle (``raw_ref``). Each upload yields
one or more ``session_streams`` (the E1 produces 4: gps/imu/wind/pressure; an
Apple Watch produces up to 6: gps + heart_rate/energy/hrv/respiration + the
optional ``race_marker`` observational start-sequence stream).
``sequence_number``/``is_final`` enable
chunked/live uploads while keeping today's single-upload case simple (0/true
defaults); streams are consolidated only when the ``is_final`` row lands.
``imports`` keeps its own ``raw_ref`` so the file is traceable even if parsing
fails before any session_upload exists.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDPKMixin, enum_check

IMPORT_STATUSES = ("pending", "processed", "failed")
UPLOAD_STATUSES = ("pending", "processing", "processed", "failed")
# Re-analysis / wind-refresh job state — separate from ``status`` above,
# which tracks the ingestion pipeline (and feeds ``sessions.rollup_status``).
# NULL means idle (no job running / last job succeeded).
REANALYSIS_STATUSES = ("running", "failed")
UPLOAD_SOURCE_TYPES = ("device", "manual_import")
UPLOAD_SUBJECT_TYPES = ("boat", "crew_member")
STREAM_SENSOR_TYPES = ("gps", "imu", "wind", "pressure", "heart_rate",
                       "energy", "hrv", "respiration", "race_marker",
                       "estimated_position", "estimated_motion", "other")
# The subset of STREAM_SENSOR_TYPES that describes a *person* rather than the
# boat — private to the upload's subject_user_id unless shared (see
# auth.session_physio_visible_to). Single source of truth for every read path
# that has to gate or group by "is this physiological data".
PHYSIO_SENSOR_TYPES = ("heart_rate", "energy", "hrv", "respiration")
# Boat sensors, plus what the pipeline derives from them: all describe the hull,
# all come from the same device as the navigation track, so they follow whichever
# upload services/nav_source.py resolves instead of being merged across uploads.
# Pairing one device's heel with another's position would fabricate a boat state
# that never existed.
#
# Everything not in here and not in PHYSIO_SENSOR_TYPES (``race_marker``,
# ``other``) is per-upload observational data with no single-valued constraint.
NAV_SENSOR_TYPES = ("gps", "imu", "wind", "pressure",
                    "estimated_position", "estimated_motion")


class ImportORM(UUIDPKMixin, Base):
    __tablename__ = "imports"
    __table_args__ = (enum_check("status", IMPORT_STATUSES),)

    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    raw_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # S3 key of raw file
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")


class SessionUploadORM(UUIDPKMixin, Base):
    __tablename__ = "session_uploads"
    __table_args__ = (
        # NULL device_id rows (manual imports) never collide (NULLS DISTINCT).
        UniqueConstraint("session_id", "device_id", "sequence_number"),
        enum_check("source_type", UPLOAD_SOURCE_TYPES),
        enum_check("subject_type", UPLOAD_SUBJECT_TYPES),
        enum_check("status", UPLOAD_STATUSES),
        enum_check("reanalysis_status", REANALYSIS_STATUSES),
        CheckConstraint(
            "(source_type = 'device' AND device_id IS NOT NULL AND import_id IS NULL)"
            " OR (source_type = 'manual_import' AND import_id IS NOT NULL AND device_id IS NULL)",
            name="source_consistent",
        ),
        # One-directional on purpose: stays valid if a crew user is later
        # deleted (subject_user_id SET NULL).
        CheckConstraint(
            "subject_type = 'crew_member' OR subject_user_id IS NULL",
            name="subject_consistent",
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    device_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), nullable=True
    )
    import_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("imports.id", ondelete="RESTRICT"), nullable=True
    )
    # Whom THIS device's data refers to: the boat or one crew member.
    subject_type: Mapped[str] = mapped_column(String, nullable=False, default="boat")
    subject_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Raw bundle of THIS device/import (S3 path/prefix).
    raw_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Chunk order for this device/import in the session (0 = single/first).
    sequence_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # False = intermediate live-tracking chunk; streams consolidate on final.
    is_final: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # Opt-in: this crew member lets the session's crew/boat managers see their
    # physiological streams (PHYSIO_SENSOR_TYPES). Private by default — same
    # shape as sessions.notes_shared, see auth.session_physio_visible_to. Lives
    # on the upload because one upload IS one crew member's physio bundle
    # (subject_type='crew_member' + subject_user_id). Meaningless, and left
    # False, on subject_type='boat' rows.
    physio_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Re-analysis / wind-refresh job tracking (``POST .../reanalyze``,
    # ``POST .../wind/refresh``) — NULL/"running"/"failed", see
    # REANALYSIS_STATUSES. Independent of ``status`` above.
    reanalysis_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reanalysis_error: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class SessionStreamORM(UUIDPKMixin, Base):
    __tablename__ = "session_streams"
    __table_args__ = (enum_check("sensor_type", STREAM_SENSOR_TYPES),)

    session_upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session_uploads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sensor_type: Mapped[str] = mapped_column(String, nullable=False)
    sample_rate_hz: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # S3 ref of the processed/normalized series (raw 10Hz data NOT in DB).
    data_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
