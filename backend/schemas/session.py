"""Session request DTOs: sessions + crew."""

import uuid
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel


class SessionWriteModel(BaseModel):
    activity_id: Optional[uuid.UUID] = None  # required on create
    boat_id: Optional[uuid.UUID] = None  # required on create
    started_at: Optional[AwareDatetime] = None
    ended_at: Optional[AwareDatetime] = None


class SessionCrewModel(BaseModel):
    user_id: uuid.UUID
    sailing_role: Literal["skipper", "crew", "guest"] = "crew"


class ManeuverCorrectionModel(BaseModel):
    # Mirrors backend/db/models/session.py::MANEUVER_TYPES — kept as a
    # literal (not imported) since schemas stay dependency-free of db/models.
    maneuver_type: Literal["tack", "gybe", "course_change"]


class ManeuverRejectionModel(BaseModel):
    rejected: bool


class ManeuverCreateModel(BaseModel):
    maneuver_type: Literal["tack", "gybe", "course_change"]
    start_time: float
    end_time: float
