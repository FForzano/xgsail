"""API request/response DTOs (Pydantic) for the SailFrames HTTP layer.

These are the *wire* shapes accepted/returned by endpoints, kept separate from
the storage-agnostic domain models in ``web/api/domain``. Endpoints translate
between the two.
"""

from .regatta import RegattaCreateModel, RegattaUpdateModel
from .raceday import RaceDayCreateModel, RaceDayUpdateModel
from .race import (
    StartFinishLineModel,
    MarkModel,
    RaceBoatModel,
    RaceCreateModel,
    RaceUpdateModel,
)
from .auth import RegisterModel, LoginModel
from .club import ClubCreateModel, ClubInviteModel, ClubJoinModel
from .group import GroupCreateModel, GroupInviteModel, GroupJoinModel
from .device import DeviceRegisterModel, DeviceAssignmentModel
from .session import SessionCrewModel, SessionCrewSlotModel
from .boat import BoatWriteModel, BoatMemberModel, BoatMemberRoleModel

__all__ = [
    "RegattaCreateModel",
    "RegattaUpdateModel",
    "RaceDayCreateModel",
    "RaceDayUpdateModel",
    "StartFinishLineModel",
    "MarkModel",
    "RaceBoatModel",
    "RaceCreateModel",
    "RaceUpdateModel",
    "RegisterModel",
    "LoginModel",
    "ClubCreateModel",
    "ClubInviteModel",
    "ClubJoinModel",
    "GroupCreateModel",
    "GroupInviteModel",
    "GroupJoinModel",
    "DeviceRegisterModel",
    "DeviceAssignmentModel",
    "SessionCrewModel",
    "SessionCrewSlotModel",
    "BoatWriteModel",
    "BoatMemberModel",
    "BoatMemberRoleModel",
]
