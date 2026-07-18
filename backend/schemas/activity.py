"""Activity + mark request DTOs."""

import uuid
from typing import Optional

from pydantic import AwareDatetime, BaseModel


class ActivityWriteModel(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None  # race | training | solo — required on create
    club_id: Optional[uuid.UUID] = None
    race_id: Optional[uuid.UUID] = None
    group_id: Optional[uuid.UUID] = None
    visibility: Optional[str] = None  # public | club | group | private
    status: Optional[str] = None  # planned | completed
    description: Optional[str] = None
    started_at: Optional[AwareDatetime] = None
    ended_at: Optional[AwareDatetime] = None


class MarkWriteModel(BaseModel):
    mark_role: Optional[str] = None  # required on create, enforced by the router
    lat: Optional[float] = None
    lng: Optional[float] = None
    set_at: Optional[AwareDatetime] = None
