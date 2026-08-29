"""User profile request DTOs, plus the progress-summary response models."""

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

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


# --- GET /users/me/progress response ------------------------------------
# One of the few endpoints with an explicit response layer: its payload is an
# aggregate, not any single row's ``to_dict()``.

class ProgressTotalsModel(BaseModel):
    sessions: int
    days: int
    distance_m: float
    duration_s: int
    boats: int
    # The caller's own active energy across the year, 0.0 when nobody wore a
    # watch. Only ever their own — see SqlSessionRepo.list_crewed_physio.
    kcal: float = 0.0


class ProgressBestModel(BaseModel):
    metric: str
    value: float
    session_id: UUID
    # The session route is nested under its activity, so a record row can only
    # link to the outing it was set on if the activity comes with it.
    activity_id: UUID
    boat_id: UUID
    boat_name: Optional[str] = None
    occurred_at: datetime


class ProgressBoatModel(BaseModel):
    boat_id: UUID
    name: Optional[str] = None
    sessions: int
    distance_m: float
    duration_s: int


class UserProgressModel(BaseModel):
    year: int
    available_years: list[int]
    totals: ProgressTotalsModel
    previous: ProgressTotalsModel
    by_month: list[int]
    previous_by_month: list[int]
    personal_bests: list[ProgressBestModel]
    by_boat: list[ProgressBoatModel]
