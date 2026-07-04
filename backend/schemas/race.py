"""Race + result request DTOs."""

import uuid
from typing import Optional

from pydantic import AwareDatetime, BaseModel


class RaceWriteModel(BaseModel):
    race_day_id: Optional[uuid.UUID] = None  # required on create
    race_number: Optional[int] = None  # required on create
    status: Optional[str] = None  # scheduled | started | finished | abandoned
    start_time: Optional[AwareDatetime] = None


class ResultWriteModel(BaseModel):
    session_id: Optional[uuid.UUID] = None
    finish_time: Optional[AwareDatetime] = None
    elapsed_time: Optional[int] = None  # seconds
    corrected_time: Optional[int] = None  # seconds
    position: Optional[int] = None
    score: Optional[float] = None
    status: str = "finished"  # finished | dnf | dns | dsq | ocs | ret
