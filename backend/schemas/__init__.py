"""API request DTOs (Pydantic) for the SailFrames HTTP layer.

These validate the *request* bodies endpoints accept. Responses are produced by
``ORM.to_dict()`` (see ``db/base.py``), so there is no parallel response-model
layer to keep in sync. All ids are UUIDs; timestamps are ``AwareDatetime``
(naive datetimes are rejected at the edge).
"""

from .auth import RegisterModel, LoginModel, ChangePasswordModel
from .user import UserUpdateModel
from .boat import (
    BoatWriteModel,
    BoatMemberModel,
    BoatMemberRoleModel,
    BoatClassWriteModel,
)
from .club import ClubWriteModel, ClubMemberModel, ClubMemberStatusModel
from .group import GroupWriteModel, GroupMemberModel, GroupMemberUpdateModel
from .device import (
    DeviceTypeWriteModel,
    ClaimRequestModel,
    ClaimConfirmModel,
    DeviceUpdateModel,
    DeviceSessionUploadCreateModel,
    DeviceUploadPatchModel,
    DeviceHealthModel,
)
from .activity import ActivityWriteModel, MarkWriteModel
from .session import SessionWriteModel, SessionCrewModel
from .regatta import RegattaWriteModel
from .raceday import RaceDayWriteModel
from .race import RaceWriteModel, ResultWriteModel
from .imports import ImportCreateModel, ImportCompleteModel
from .rbac import UserRoleGrantModel
from .wind import WindStationWriteModel, WindFetchModel
from .polar import PolarPointModel, PolarUpsertModel

__all__ = [
    "RegisterModel",
    "LoginModel",
    "ChangePasswordModel",
    "UserUpdateModel",
    "BoatWriteModel",
    "BoatMemberModel",
    "BoatMemberRoleModel",
    "BoatClassWriteModel",
    "ClubWriteModel",
    "ClubMemberModel",
    "ClubMemberStatusModel",
    "GroupWriteModel",
    "GroupMemberModel",
    "GroupMemberUpdateModel",
    "DeviceTypeWriteModel",
    "ClaimRequestModel",
    "ClaimConfirmModel",
    "DeviceUpdateModel",
    "DeviceSessionUploadCreateModel",
    "DeviceUploadPatchModel",
    "DeviceHealthModel",
    "ActivityWriteModel",
    "MarkWriteModel",
    "SessionWriteModel",
    "SessionCrewModel",
    "RegattaWriteModel",
    "RaceDayWriteModel",
    "RaceWriteModel",
    "ResultWriteModel",
    "ImportCreateModel",
    "ImportCompleteModel",
    "UserRoleGrantModel",
    "WindStationWriteModel",
    "WindFetchModel",
    "PolarPointModel",
    "PolarUpsertModel",
]
