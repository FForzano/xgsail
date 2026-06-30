"""Boat domain model — a catalog entry persistent across races."""

from typing import Optional

from pydantic import Field

from .base import DomainModel


class Boat(DomainModel):
    boat_id: str
    name: str = ""
    type: str = ""
    sail_number: str = ""
    club: str = ""
    loa_m: Optional[float] = None
    skippers: list[dict] = Field(default_factory=list)
    photos: dict = Field(default_factory=dict)
    cert_url: Optional[str] = None
    mbsa_url: Optional[str] = None
    links: list[dict] = Field(default_factory=list)
    notes: str = ""
    polar: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
