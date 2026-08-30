"""Club request DTOs: clubs + user_clubs membership."""

import re
import uuid
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel

from ..richtext import RichTextBasic

# "{osm_type}/{osm_id}" — the exact string the frontend uses as NauticalPoi.id.
_OSM_REF_RE = re.compile(r"^(node|way|relation)/[1-9][0-9]*$")


def _validate_osm_ref(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not _OSM_REF_RE.match(value):
        raise ValueError("osm_ref must be '{node|way|relation}/{positive id}'")
    return value


# On the DTO type rather than in the router, matching how prose fields validate
# (see backend/richtext.py): every endpoint taking the field gets the check for
# free, and a malformed ref fails as a 422 before it can be stored as junk that
# would never match a POI.
OsmRef = Annotated[Optional[str], AfterValidator(_validate_osm_ref)]


class ClubWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    description: RichTextBasic = None
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
    osm_ref: OsmRef = None
    is_active: Optional[bool] = None


class ClubMemberModel(BaseModel):
    user_id: Optional[uuid.UUID] = None  # omitted = the caller joins themselves
    status: Optional[str] = None  # invited | active | deleted


class ClubMemberStatusModel(BaseModel):
    status: str
