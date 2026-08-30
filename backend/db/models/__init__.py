"""SQLAlchemy ORM models — er-project schema (see docs/er-project.md).

One module per aggregate. Importing this package registers every table on
``Base.metadata`` so Alembic autogenerate (and ``init_db()``) sees them.
"""

from .app_config import AppConfigORM
from .media import ImageORM, FileORM
from .user import UserORM, AuthRefreshTokenORM
from .rbac import RoleORM, PermissionORM, RolePermissionORM, UserRoleORM
from .club import ClubORM, UserClubORM
from .group import GroupORM, UserGroupORM
from .post import PostORM, PostImageORM
from .boat import BoatClassORM, BoatORM, UserBoatORM, BoatPhotoORM, BoatNoteORM
from .boat_claim import BoatClaimORM
from .polar import PolarPointORM
from .device import DeviceTypeORM, DeviceORM
from .integration import IntegrationConnectionORM
from .note_template import NoteTemplateORM
from .race import (
    OfficialStandingsORM, RegattaORM, RegattaDivisionORM, RegattaEntryORM,
    RaceDayORM, RaceORM, ResultORM,
)
from .activity import ActivityORM, MarkORM
from .live_recording import LiveRecordingORM
from .session import (
    SessionORM,
    SessionCrewORM,
    SessionPhotoORM,
    SessionVideoORM,
    SessionStatsORM,
    SessionPhysioStatsORM,
    SessionManeuverORM,
    SessionLegORM,
    SessionAnalysisORM,
)
from .ingest import ImportORM, SessionUploadORM, SessionStreamORM
from .wind import WindStationORM, WindObservationORM, WindEstimateORM

__all__ = [
    "AppConfigORM",
    "ImageORM",
    "FileORM",
    "UserORM",
    "AuthRefreshTokenORM",
    "RoleORM",
    "PermissionORM",
    "RolePermissionORM",
    "UserRoleORM",
    "ClubORM",
    "UserClubORM",
    "GroupORM",
    "UserGroupORM",
    "PostORM",
    "PostImageORM",
    "BoatClassORM",
    "BoatORM",
    "UserBoatORM",
    "BoatPhotoORM",
    "BoatNoteORM",
    "BoatClaimORM",
    "PolarPointORM",
    "DeviceTypeORM",
    "DeviceORM",
    "IntegrationConnectionORM",
    "NoteTemplateORM",
    "RegattaORM",
    "RegattaDivisionORM",
    "RegattaEntryORM",
    "OfficialStandingsORM",
    "RaceDayORM",
    "RaceORM",
    "ResultORM",
    "ActivityORM",
    "MarkORM",
    "LiveRecordingORM",
    "SessionORM",
    "SessionCrewORM",
    "SessionPhotoORM",
    "SessionVideoORM",
    "SessionStatsORM",
    "SessionPhysioStatsORM",
    "SessionManeuverORM",
    "SessionLegORM",
    "SessionAnalysisORM",
    "ImportORM",
    "SessionUploadORM",
    "SessionStreamORM",
    "WindStationORM",
    "WindObservationORM",
    "WindEstimateORM",
]
