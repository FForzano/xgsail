"""Session domain model — recorded data from one device on one date.

Only the manifest-level metadata lives here; the bulk sensor payloads
(nav/imu/wind/pres) always stay in the blob store, never the DB.
"""

from typing import Any, Optional

from .base import DomainModel


class Session(DomainModel):
    device_id: str
    date: str
    session_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_sec: Optional[int] = None
    boat: Optional[str] = None
    name: Optional[str] = None
    sensors: Any = None
    has_video: bool = False
    has_analysis: bool = False
    trim: Optional[dict] = None
