"""Boat request DTOs: boats, user_boats membership, boat_classes."""

import uuid
from typing import Optional

from pydantic import BaseModel


class BoatWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    boat_class_id: Optional[uuid.UUID] = None
    sail_number: Optional[str] = None
    loa_m: Optional[float] = None
    notes: Optional[str] = None
    club_id: Optional[uuid.UUID] = None


class BoatMemberModel(BaseModel):
    user_id: uuid.UUID
    role: str = "visitor"  # owner | admin | visitor
    default_sailing_role: Optional[str] = None  # skipper | crew


class BoatMemberRoleModel(BaseModel):
    role: str


class BoatClassWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    description: Optional[str] = None
