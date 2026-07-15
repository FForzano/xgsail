"""Wind/meteo tables — two distinct concepts, not one:

- ``wind_stations`` + ``wind_observations``: raw acquisition from real,
  fixed-position sensors only (NOAA NDBC/METAR, a club's custom device).
  Algorithmic APIs with no fixed position and their own accessible history
  (Open-Meteo) are never persisted here — they're queried on demand (see
  ``services/wind_providers/open_meteo.py``) since there's nothing to cache:
  any lat/lng, any past date, always available from the provider itself.
  ``keeps_local_history`` is per-station: real sensors whose own retention
  window is short (NDBC/METAR trim their public history) need us to keep
  what we've fetched; a future provider with its own full history wouldn't.
- ``wind_estimates``: the *determined* wind for a place and time — a
  spatiotemporal grid, not tied to one session, so sessions that pass
  through the same cell/time share (and refine) the same estimate. How raw
  observations turn into (or refine) a cell's estimate is a pluggable
  algorithm — see ``services/wind_estimate_refinement.py`` — deliberately
  left as a skeleton here.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDPKMixin, enum_check

WIND_PROVIDERS = ("noaa_ndbc", "noaa_metar", "custom_device", "cumulus_realtime",
                  "cumulus_gauges_json")
WIND_STATION_TYPES = ("buoy", "metar", "custom_device")


class WindStationORM(UUIDPKMixin, Base):
    __tablename__ = "wind_stations"
    __table_args__ = (
        UniqueConstraint("provider", "external_station_id"),
        enum_check("provider", WIND_PROVIDERS),
        enum_check("station_type", WIND_STATION_TYPES),
    )

    provider: Mapped[str] = mapped_column(String, nullable=False)
    external_station_id: Mapped[str] = mapped_column(String, nullable=False)  # "44013", "KBOS"
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    station_type: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Whether we need to persist this station's readings ourselves (its own
    # history isn't reliably accessible later) or can always query it live.
    # True for every provider today (NDBC/METAR/custom_device all have a
    # short or no public retention window).
    keeps_local_history: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # URL to poll for providers whose station is a live endpoint rather than
    # a fixed API keyed by external_station_id (e.g. cumulus_realtime,
    # cumulus_gauges_json).
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class WindObservationORM(UUIDPKMixin, Base):
    """A raw reading from a real, fixed-position station — never Open-Meteo
    or any other algorithmic/position-agnostic API (see module docstring)."""

    __tablename__ = "wind_observations"
    __table_args__ = (
        # Unique keeps the periodic fetch job idempotent; doubles as the
        # (station, observed_at) lookup index for time-range queries.
        UniqueConstraint("wind_station_id", "observed_at"),
    )

    wind_station_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wind_stations.id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    twd_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tws_kts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gust_kts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WindEstimateORM(UUIDPKMixin, Base):
    """The determined wind for one spatiotemporal grid cell — refined over
    time as new raw observations (real stations, onboard sensors passing
    through, Open-Meteo models) land in that cell/bucket. Cell size and
    bucket width are runtime constants (see ``services/wind_estimates.py``),
    not encoded here — this table just stores whatever key they produce."""

    __tablename__ = "wind_estimates"
    __table_args__ = (
        UniqueConstraint("grid_lat", "grid_lng", "time_bucket"),
    )

    grid_lat: Mapped[float] = mapped_column(Float, nullable=False)
    grid_lng: Mapped[float] = mapped_column(Float, nullable=False)
    time_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    twd_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tws_kts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gust_kts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Meaning left entirely to the refinement algorithm (see
    # services/wind_estimate_refinement.py) — not interpreted anywhere else.
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Every observation that contributed, e.g.
    # [{"type": "onboard_sensor", "session_id": "...", "observed_at": "..."},
    #  {"type": "open_meteo", "model": "icon_d2", "observed_at": "..."}]
    sources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    refined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
