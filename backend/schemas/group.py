"""Group request DTOs: groups + user_groups membership."""

import uuid
from typing import Optional

from pydantic import BaseModel


class GroupWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    description: Optional[str] = None
    visibility: Optional[str] = None  # public | private


class GroupMemberModel(BaseModel):
    user_id: Optional[uuid.UUID] = None  # omitted = the caller joins themselves
    role: str = "member"  # owner | admin | member


class GroupMemberUpdateModel(BaseModel):
    role: Optional[str] = None  # owner | admin | member (owner-only change)
    status: Optional[str] = None  # invited | active (self-accept or manager)
