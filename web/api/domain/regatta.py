"""Regatta domain model — a multi-day series grouping race days and races."""

from typing import Any, Optional

from pydantic import Field

from .base import DomainModel


class Regatta(DomainModel):
    regatta_id: str
    name: str
    venue: str = ""
    boat_class: Any = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    rating_system: Optional[str] = None
    start_sequence_minutes: Optional[int] = None
    race_ids: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
