"""User profile request DTOs."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class UserUpdateModel(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[date] = None
    password: Optional[str] = None  # change-password path (router re-hashes)
    unit_system: Optional[Literal["nautical", "metric"]] = None
    # Optional, and used only to derive heart-rate zones (services/hr_zones.py).
    # Bounded so a mistyped value can't produce absurd zones: a resting rate
    # outside 30–120 or a maximum outside 100–240 is a typo, not a person.
    resting_hr_bpm: Optional[int] = Field(default=None, ge=30, le=120)
    max_hr_bpm: Optional[int] = Field(default=None, ge=100, le=240)
