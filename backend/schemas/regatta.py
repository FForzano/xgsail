"""Regatta request DTOs."""

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class RegattaEntryWriteModel(BaseModel):
    """Organizer putting a boat on the start list."""

    boat_id: uuid.UUID


class RegattaJoinModel(BaseModel):
    """Sailor self-entering with the share code. ``boat_id`` must be a boat
    they own/administer — the code grants entry, not the right to enter
    someone else's boat."""

    code: str = Field(min_length=1, max_length=32)
    boat_id: uuid.UUID


class RegattaWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    description: Optional[str] = None
    club_id: Optional[uuid.UUID] = None  # required on create
    class_id: Optional[uuid.UUID] = None
    scoring_system: Optional[str] = None  # low_point | bonus_point | custom
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None  # scheduled | active | completed
