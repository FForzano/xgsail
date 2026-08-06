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
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, UUIDPKMixin, enum_check

SESSION_STATUSES = ("pending", "processing", "processed", "failed")
SESSION_SAILING_ROLES = ("skipper", "crew", "guest")
# "course_change" is a significant course change that isn't a tack or gybe.
# Allowed by the schema but not produced by the current worker (the geometric
# classifier only emits tack/gybe) — reserved for the future ML classifier.
MANEUVER_TYPES = ("tack", "gybe", "course_change")
MANEUVER_SOURCES = ("detected", "manual")
LEG_TYPES = ("upwind", "downwind", "reach")
TACK_SIDES = ("port", "starboard")


class SessionORM(UUIDPKMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (enum_check("status", SESSION_STATUSES),)
    # Search mirror only: `notes` is HTML, and a LIKE over markup would match
    # tag names and entities. Never served — clients read `notes`.
    __wire_exclude__ = ("notes_plain",)

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
    # Reversible track trim (unix-epoch seconds, same convention as
    # session_maneuvers.start_time). Null = no trim, analyze the full track.
    # Raw gps.json is never touched — a reanalysis just slices the parsed
    # points to this window before running the pipeline (see
    # workers/process_upload/analyzer.py::_slice_by_time). Adjustable any time.
    trim_start_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trim_end_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Free-text crew log: boat setup, waves, wind perception, how the trim
    # felt, what to try next time — shared by and editable by any crew
    # member (see auth.is_session_crew_or_manager), not per-author. Private
    # to the crew/boat managers unless notes_shared is set (see
    # auth.session_notes_visible_to).
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes_plain: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Which upload's GPS is THE track of this session. A session can receive
    # several gps streams at once (a boat tracker + one Apple Watch per crew
    # member), but navigation must be single-valued: the map, the GPX export,
    # the replay endpoints and the analysis pipeline all read the one resolved
    # here. NULL = no explicit choice, apply the deterministic ranking in
    # services/nav_source.py. On the session (not a flag on the uploads) so
    # "two primaries" / "no primary" are unrepresentable. Physiological streams
    # are NOT deduplicated this way — every crew member keeps their own.
    # use_alter breaks the sessions<->session_uploads FK cycle
    # (session_uploads.session_id -> sessions): added by a separate ALTER once
    # both tables exist, same trick as users.profile_image_id.
    primary_nav_upload_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("session_uploads.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )


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


class SessionPhysioStatsORM(Base):
    """Aggregate physiological stats of ONE crew member for ONE session — PK is
    their upload, so a boat with two watches aboard gets two rows.

    Deliberately not columns on ``session_stats``: that table is 1:1 with the
    session (two wearers would collide) and is served to everyone who can see
    the session, whereas these numbers go through
    ``auth.session_physio_visible_to``. Every column is nullable because the
    four physio files (hr/energy/hrv/respiration) arrive as independent worker
    callbacks and fill this row progressively.

    Heart-rate *zones* are deliberately absent: they depend on profile data the
    user can correct after the fact, so they're derived per request in
    ``services/hr_zones.py`` rather than frozen here.
    """

    __tablename__ = "session_physio_stats"

    session_upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session_uploads.id", ondelete="CASCADE"), primary_key=True
    )
    avg_hr_bpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_hr_bpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_hr_bpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Active energy actually burned over the session — the watch reports a
    # cumulative counter, the worker turns it into this total (see
    # workers/process_upload/processing/physio.py).
    total_kcal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_kcal_per_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_hrv_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_resp_brpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Span actually covered by heart-rate samples — can be shorter than the
    # session (watch started late, battery died, sensor lost contact).
    hr_duration_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SessionManeuverORM(UUIDPKMixin, Base):
    """One detected tack/gybe. Discrete, finite per session (a handful to a few
    dozen) — normalized into rows so it stays queryable, unlike the series/
    matrix parts of the analysis which live in ``session_analysis`` as JSON.
    ``*_time`` are unix-epoch seconds (the worker's native shape), not TZ."""

    __tablename__ = "session_maneuvers"
    __table_args__ = (
        enum_check("maneuver_type", MANEUVER_TYPES),
        enum_check("original_maneuver_type", MANEUVER_TYPES),
        enum_check("source", MANEUVER_SOURCES),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    maneuver_type: Mapped[str] = mapped_column(String, nullable=False)
    # 'detected' = pipeline output (the default; every row before this column
    # existed). 'manual' = user-added via POST .../maneuvers — see
    # routers/sessions.py::add_maneuver and services/maneuver_reconciliation.py
    # for how source/corrected_by_user/rejected together decide which rows a
    # reanalysis is allowed to delete/replace.
    source: Mapped[str] = mapped_column(String, nullable=False, default="detected")
    # User said "this proposed maneuver isn't real" — kept as a tombstone
    # (not deleted) so a later reanalysis's re-detection of the same event
    # doesn't resurrect it as a fresh row. Only meaningful for source=
    # 'detected' rows (manual rows are hard-deleted instead, see
    # routers/sessions.py::delete_maneuver).
    rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True between a manual maneuver's creation (stat columns are 0.0
    # sentinels) and the worker's async computation of its real stats/
    # features landing via POST /api/system/maneuvers/{id}/computed. Never
    # true for source='detected' rows (the worker always computes stats
    # before those are ever persisted).
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Frozen at whatever the pipeline/classifier assigned on insert — never
    # touched by a user correction (unlike `maneuver_type`, which a user
    # correction overwrites). This is the ground-truth provenance signal for
    # training data export: `maneuver_type != original_maneuver_type` means a
    # human corrected this row. See `corrected_by_user` for the same fact as
    # a direct flag, and routers/sessions.py::correct_maneuver.
    original_maneuver_type: Mapped[str] = mapped_column(String, nullable=False)
    corrected_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    speed_loss_kts: Mapped[float] = mapped_column(Float, nullable=False)
    speed_before_kts: Mapped[float] = mapped_column(Float, nullable=False)
    speed_min_kts: Mapped[float] = mapped_column(Float, nullable=False)
    speed_after_kts: Mapped[float] = mapped_column(Float, nullable=False)
    recovery_time_sec: Mapped[float] = mapped_column(Float, nullable=False)
    heading_change_deg: Mapped[float] = mapped_column(Float, nullable=False)
    distance_lost_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Statistical feature vector computed at detection (see the worker's
    # processing/maneuver_features.py) — persisted to accumulate a training
    # dataset for the future ML maneuver classifier. Nullable: older rows and
    # analyses without features leave it null. Metrics that characterize the
    # maneuver itself rather than this specific occurrence (e.g. max heel,
    # under the "max_heel_deg" key) live ONLY here, not as their own column.
    features: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


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
