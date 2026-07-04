"""Session request DTOs: sessions + crew."""

import uuid
from typing import Optional

from pydantic import AwareDatetime, BaseModel


class SessionWriteModel(BaseModel):
    activity_id: Optional[uuid.UUID] = None  # required on create
    boat_id: Optional[uuid.UUID] = None  # required on create
    started_at: Optional[AwareDatetime] = None
    ended_at: Optional[AwareDatetime] = None


class SessionCrewModel(BaseModel):
    user_id: uuid.UUID
    sailing_role: str = "crew"  # skipper | crew | guest
