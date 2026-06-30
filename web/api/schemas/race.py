"""Race request DTOs (and the nested line/mark/boat input shapes)."""

from typing import Optional

from pydantic import BaseModel


class StartFinishLineModel(BaseModel):
    pin_lat: float
    pin_lon: float
    boat_lat: float
    boat_lon: float


class MarkModel(BaseModel):
    mark_id: str
    name: str = ""
    mark_type: str = "custom"  # windward|leeward|gate_port|gate_stbd|offset|custom
    lat: float
    lon: float


class RaceBoatModel(BaseModel):
    device_id: str
    boat_name: str
    sail_number: str = ""
    session_path: Optional[str] = None
    gpx_path: Optional[str] = None  # Set after GPX track upload


class RaceCreateModel(BaseModel):
    name: str
    date: str  # YYYY-MM-DD
    start_time: str  # ISO timestamp
    end_time: str  # ISO timestamp
    regatta_id: Optional[str] = None
    raceday_id: Optional[str] = None
    boats: list[RaceBoatModel] = []
    start_line: Optional[StartFinishLineModel] = None
    finish_line: Optional[StartFinishLineModel] = None
    marks: list[MarkModel] = []
    course: list[str] = []
    finish_order: list[str] = []


class RaceUpdateModel(BaseModel):
    name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    boats: Optional[list[RaceBoatModel]] = None
    start_line: Optional[StartFinishLineModel] = None
    finish_line: Optional[StartFinishLineModel] = None
    marks: Optional[list[MarkModel]] = None
    course: Optional[list[str]] = None
    finish_order: Optional[list[str]] = None
    raceday_id: Optional[str] = None
