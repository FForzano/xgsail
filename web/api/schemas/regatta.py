"""Regatta request DTOs."""

from typing import Optional

from pydantic import BaseModel


class RegattaCreateModel(BaseModel):
    name: str
    venue: str
    boat_class: str
    start_date: str
    end_date: str


class RegattaUpdateModel(BaseModel):
    name: Optional[str] = None
    venue: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
