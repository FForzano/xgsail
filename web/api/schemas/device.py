"""Device request DTOs."""

from typing import Optional

from pydantic import BaseModel


class DeviceRegisterModel(BaseModel):
    name: Optional[str] = None
    device_type: str = "sailframes_e"  # sailframes_e | sailframes_b | external
    owner_type: str = "user"  # user | club
    # Boat-private device (owner_type=user): the boat it lives on.
    default_boat_id: Optional[str] = None
    # Club/RC device (owner_type=club): the owning club.
    owned_by_club_id: Optional[int] = None


class DeviceAssignmentModel(BaseModel):
    boat_id: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    regatta_id: Optional[str] = None
    race_id: Optional[str] = None
