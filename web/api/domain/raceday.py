"""RaceDay domain model — a single day of racing or training."""

from typing import Optional

from pydantic import Field

from .base import DomainModel


class RaceDay(DomainModel):
    raceday_id: str
    date: str
    type: str = "race_day"  # race_day | training_day
    name: Optional[str] = None
    regatta_id: Optional[str] = None
    race_ids: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
