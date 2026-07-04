"""Device request DTOs: claim flow + management + device-key upload API.

Shapes follow docs/device-protocol.md to the letter — firmware is written
against these."""

import uuid
from typing import Optional

from pydantic import AwareDatetime, BaseModel


class DeviceTypeWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    category: Optional[str] = None  # boat_tracker | wearable
    default_sensors: Optional[list] = None
    parser_key: Optional[str] = None


class ClaimRequestModel(BaseModel):
    device_type_id: uuid.UUID
    nickname: Optional[str] = None
    # Claim target — the router requires exactly one of the three.
    owner_user_id: Optional[uuid.UUID] = None
    owner_boat_id: Optional[uuid.UUID] = None
    owner_club_id: Optional[uuid.UUID] = None


class ClaimConfirmModel(BaseModel):
    external_id: str
    claim_code: str


class DeviceUpdateModel(BaseModel):
    nickname: Optional[str] = None


class DeviceSessionUploadCreateModel(BaseModel):
    boat_id: Optional[uuid.UUID] = None  # default: devices.owner_boat_id (boat_tracker)
    activity_id: Optional[uuid.UUID] = None
    started_at: AwareDatetime
    ended_at: Optional[AwareDatetime] = None
    sequence_number: int = 0
    is_final: bool = True
    subject_type: str = "boat"  # boat | crew_member
    subject_user_id: Optional[uuid.UUID] = None
    filename: str = "data.csv"  # bundle object name under raw/uploads/{id}/


class DeviceUploadPatchModel(BaseModel):
    is_final: Optional[bool] = None
    status: Optional[str] = None  # only "failed" is accepted from devices


class DeviceHealthModel(BaseModel):
    battery_pct: Optional[float] = None
    battery_v: Optional[float] = None
    heap_free: Optional[int] = None
    firmware_version: Optional[str] = None
    uptime_s: Optional[int] = None
