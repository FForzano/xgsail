"""Club request DTOs: clubs + user_clubs membership."""

import uuid
from typing import Optional

from pydantic import BaseModel


class ClubWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    description: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None  # ISO 3166-1 alpha-2
    lat: Optional[float] = None
    lng: Optional[float] = None
    founded_year: Optional[int] = None
    website: Optional[str] = None
    contact_email: Optional[str] = None
    is_active: Optional[bool] = None


class ClubMemberModel(BaseModel):
    user_id: Optional[uuid.UUID] = None  # omitted = the caller joins themselves
    status: Optional[str] = None  # invited | active | deleted


class ClubMemberStatusModel(BaseModel):
    status: str
