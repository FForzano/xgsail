"""Session tables: ``sessions`` + crew/media/stats children.

A session is one boat's participation in an activity. It carries no
source/device columns — a session can receive data from several devices at
once (the E1 on the boat + a smartwatch per crew member), so that relation
lives in ``session_uploads`` (see ``ingest.py``). ``status`` is the aggregate
of the linked uploads' statuses. Raw 10Hz series stay in object storage
(referenced by ``session_streams.data_ref``); the DB indexes metadata only.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, UUIDPKMixin, enum_check

SESSION_STATUSES = ("pending", "processing", "processed", "failed")
SESSION_SAILING_ROLES = ("skipper", "crew", "guest")
MANEUVER_TYPES = ("tack", "gybe")
LEG_TYPES = ("upwind", "downwind", "reach")
TACK_SIDES = ("port", "starboard")


class SessionORM(UUIDPKMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (enum_check("status", SESSION_STATUSES),)

    activity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # RESTRICT: a boat with recorded sessions cannot be hard-deleted.
    boat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("boats.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Derived/aggregated from the statuses of the linked session_uploads.
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")


class SessionCrewORM(UUIDPKMixin, CreatedAtMixin, Base):
    """Who was actually aboard for THIS outing — distinct from the default in
    ``user_boats.default_sailing_role``. The user need not be linked to the
    boat in ``user_boats`` (e.g. occasional guest)."""

    __tablename__ = "session_crew"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id"),
        enum_check("sailing_role", SESSION_SAILING_ROLES),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    sailing_role: Mapped[str] = mapped_column(String, nullable=False, default="crew")


class SessionPhotoORM(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "session_photos"
    __table_args__ = (UniqueConstraint("session_id", "image_id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), nullable=False
    )
    # Who uploaded it (can be a crew member).
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SessionVideoORM(UUIDPKMixin, CreatedAtMixin, Base):
    """Videos go through ``files`` (not ``images``) — the generic non-image
    blob entity already used for boats.cert_id/mbsa_id."""

    __tablename__ = "session_videos"
    __table_args__ = (UniqueConstraint("session_id", "file_id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SessionStatsORM(Base):
    """1:1 aggregate stats — PK is the session itself, no surrogate id."""

    __tablename__ = "session_stats"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    distance_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_speed_kts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_speed_kts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Require wind data (onboard or wind_observations).
    avg_polar_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_polar_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SessionManeuverORM(UUIDPKMixin, Base):
    """One detected tack/gybe. Discrete, finite per session (a handful to a few
    dozen) — normalized into rows so it stays queryable, unlike the series/
    matrix parts of the analysis which live in ``session_analysis`` as JSON.
    ``*_time`` are unix-epoch seconds (the worker's native shape), not TZ."""

    __tablename__ = "session_maneuvers"
    __table_args__ = (enum_check("maneuver_type", MANEUVER_TYPES),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    maneuver_type: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    speed_loss_kts: Mapped[float] = mapped_column(Float, nullable=False)
    speed_before_kts: Mapped[float] = mapped_column(Float, nullable=False)
    speed_min_kts: Mapped[float] = mapped_column(Float, nullable=False)
    speed_after_kts: Mapped[float] = mapped_column(Float, nullable=False)
    recovery_time_sec: Mapped[float] = mapped_column(Float, nullable=False)
    heading_change_deg: Mapped[float] = mapped_column(Float, nullable=False)
    max_heel_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_lost_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class SessionLegORM(UUIDPKMixin, Base):
    """One straight-line leg between maneuvers (upwind/downwind/reach). Same
    rationale as ``session_maneuvers``: discrete and queryable."""

    __tablename__ = "session_legs"
    __table_args__ = (enum_check("leg_type", LEG_TYPES), enum_check("tack", TACK_SIDES))

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leg_type: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    distance_nm: Mapped[float] = mapped_column(Float, nullable=False)
    avg_speed_kts: Mapped[float] = mapped_column(Float, nullable=False)
    max_speed_kts: Mapped[float] = mapped_column(Float, nullable=False)
    avg_vmg_kts: Mapped[float] = mapped_column(Float, nullable=False)
    avg_heel_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_twa_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Which side the wind is on (sign of the *signed* mean TWA before the
    # abs() that produces avg_twa_deg above) — port/starboard, not derivable
    # from avg_twa_deg alone since that's already unsigned. Null if the leg
    # had no true-wind data to classify from (see segment_legs).
    tack: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    std_heading_deg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    num_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    end_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    end_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class SessionAnalysisORM(Base):
    """The parts of the analysis that aren't naturally relational — a small
    correlation matrix, per-maneuver-type distributions, and the VMG/true-wind
    series — kept as JSON (1:1 with the session). Scalars live in
    ``session_stats``, the polar curve in ``polar_points``, discrete events in
    ``session_maneuvers``/``session_legs``."""

    __tablename__ = "session_analysis"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    correlations: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    violin: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    maneuver_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    leg_comparison: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Per-variable distributions (speed/apparent wind/heel/pitch mean-max-std).
    sensor_stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    vmg_series: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Max-speed-per-bucket "target" polar (vs. the avg/actual polar in
    # `polar_points`) — same shape, kept alongside the other derived series
    # rather than as its own table since it isn't a relational/queryable datum.
    polar_target: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Per-timestamp true wind (twd_deg/tws_kts/source) this session's own
    # analysis settled on — see workers/process_upload/processing/
    # wind_estimation.py. The map/session views prefer this over the
    # ephemeral WindCard/live snapshot (services/wind_lookup.live_snapshot)
    # when present, since it's what VMG/polar/legs were actually computed
    # against.
    true_wind: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Small track-preview PNG rendered once by the worker from gps.json, so
    # the sessions list can show it without re-rendering the track per view.
    thumbnail_image_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
