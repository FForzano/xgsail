"""Wind/meteo tables: ``wind_stations`` + ``wind_observations``.

Local cache of external providers (NOAA NDBC/METAR, Open-Meteo) or a custom
fixed station at the club — avoids re-fetching on every render and preserves
history past the upstream API's retention window. ``observed_at`` is the
weather timestamp; ``fetched_at`` when we downloaded it (audit/cache). Which
station(s) to aggregate for a regatta/session is decided at runtime, not
persisted here.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDPKMixin, enum_check

WIND_PROVIDERS = ("noaa_ndbc", "noaa_metar", "open_meteo", "custom_device")
WIND_STATION_TYPES = ("buoy", "metar", "forecast_grid", "custom_device")


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


class WindObservationORM(UUIDPKMixin, Base):
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
