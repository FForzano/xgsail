"""Race-day request DTOs."""

from typing import Optional

from pydantic import BaseModel


class RaceDayCreateModel(BaseModel):
    date: str  # YYYY-MM-DD
    type: str = "race_day"  # "race_day" | "training_day"
    name: Optional[str] = None
    regatta_id: Optional[str] = None


class RaceDayUpdateModel(BaseModel):
    date: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None
    regatta_id: Optional[str] = None
