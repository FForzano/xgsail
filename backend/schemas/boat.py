"""Boat request DTOs: boats, user_boats membership, boat_classes."""

import uuid
from typing import Optional

from pydantic import BaseModel

from ..richtext import RichTextBasic, RichTextFull


class BoatWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    boat_class_id: Optional[uuid.UUID] = None
    sail_number: Optional[str] = None
    loa_m: Optional[float] = None
    club_id: Optional[uuid.UUID] = None
    # Honoured on create only: the repository's update path ignores it, so a
    # boat can never gain or lose placeholder status through a plain edit.
    is_guest: Optional[bool] = None


class BoatClaimCreateModel(BaseModel):
    """Claiming a guest boat. ``target_boat_id`` names the claimant's own boat
    to merge the guest into; omitted/NULL means promote the guest boat itself."""

    target_boat_id: Optional[uuid.UUID] = None


class BoatMemberModel(BaseModel):
    user_id: uuid.UUID
    role: str = "visitor"  # owner | admin | visitor
    default_sailing_role: Optional[str] = None  # skipper | crew


class BoatMemberRoleModel(BaseModel):
    role: Optional[str] = None  # owner | admin | visitor
    default_sailing_role: Optional[str] = None  # skipper | crew


class BoatNoteCreateModel(BaseModel):
    title: str
    body: RichTextFull


class BoatNoteUpdateModel(BaseModel):
    title: Optional[str] = None
    body: RichTextFull = None


class BoatNoteOrderModel(BaseModel):
    note_ids: list[uuid.UUID]


class BoatClassWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    description: RichTextBasic = None
    loa_m: Optional[float] = None
    beam_m: Optional[float] = None
    sail_area_sqm: Optional[float] = None
    crew_size: Optional[int] = None
    hull_type: Optional[str] = None  # monohull | multihull
    rig_type: Optional[str] = None  # sloop | una (RYA "Rig" column: S/U)
    spinnaker_type: Optional[str] = None  # none | asymmetric | symmetric (RYA "Spinnaker": 0/A/C)
    py_rating: Optional[int] = None  # RYA "Number" column
    rya_class_id: Optional[int] = None  # official RYA Class ID, reference only
