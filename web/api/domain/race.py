"""Race domain aggregate and its value objects.

A ``Race`` owns its course (``Mark`` list), entrants (``RaceBoat`` list),
start/finish lines, and optional computed ``RaceResult``.
"""

from typing import Optional

from pydantic import Field

from .base import DomainModel


class StartFinishLine(DomainModel):
    pin_lat: float
    pin_lon: float
    boat_lat: float
    boat_lon: float


class Mark(DomainModel):
    mark_id: str
    name: str = ""
    mark_type: str = "custom"  # windward|leeward|gate_port|gate_stbd|offset|custom
    lat: float
    lon: float


class RaceBoat(DomainModel):
    device_id: str
    boat_name: str = ""
    sail_number: str = ""
    boat_id: Optional[str] = None
    session_path: Optional[str] = None
    gpx_path: Optional[str] = None
    polar: Optional[dict] = None


class RaceResult(DomainModel):
    finish_order: list[str] = Field(default_factory=list)
    boat_results: dict = Field(default_factory=dict)
    computed_at: Optional[str] = None


class Race(DomainModel):
    race_id: str
    name: str
    date: str
    start_time: str
    end_time: str
    regatta_id: Optional[str] = None
    raceday_id: Optional[str] = None
    boats: list[RaceBoat] = Field(default_factory=list)
    start_line: Optional[StartFinishLine] = None
    finish_line: Optional[StartFinishLine] = None
    marks: list[Mark] = Field(default_factory=list)
    course: list[str] = Field(default_factory=list)
    finish_order: list[str] = Field(default_factory=list)
    results: Optional[RaceResult] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
