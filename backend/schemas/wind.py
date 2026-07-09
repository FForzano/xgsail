"""Wind station request DTOs."""

from typing import Optional

from pydantic import BaseModel


class WindStationWriteModel(BaseModel):
    provider: Optional[str] = None  # noaa_ndbc | noaa_metar | custom_device
    external_station_id: Optional[str] = None
    name: Optional[str] = None
    station_type: Optional[str] = None  # buoy | metar | custom_device
    lat: Optional[float] = None
    lng: Optional[float] = None
    keeps_local_history: Optional[bool] = None


class WindFetchModel(BaseModel):
    provider: Optional[str] = None  # None = all providers with stations
