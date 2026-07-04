"""Regatta request DTOs."""

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel


class RegattaWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    description: Optional[str] = None
    club_id: Optional[uuid.UUID] = None  # required on create
    class_id: Optional[uuid.UUID] = None
    scoring_system: Optional[str] = None  # low_point | bonus_point | custom
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None  # scheduled | active | completed
