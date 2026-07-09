"""SQLAlchemy ORM models — er-project schema (see docs/er-project.md).

One module per aggregate. Importing this package registers every table on
``Base.metadata`` so Alembic autogenerate (and ``init_db()``) sees them.
"""

from .media import ImageORM, FileORM
from .user import UserORM, AuthRefreshTokenORM
from .rbac import RoleORM, PermissionORM, RolePermissionORM, UserRoleORM
from .club import ClubORM, UserClubORM
from .group import GroupORM, UserGroupORM
from .boat import BoatClassORM, BoatORM, UserBoatORM, BoatPhotoORM
from .polar import PolarPointORM
from .device import DeviceTypeORM, DeviceORM
from .race import RegattaORM, RaceDayORM, RaceORM, ResultORM
from .activity import ActivityORM, MarkORM
from .session import (
    SessionORM,
    SessionCrewORM,
    SessionPhotoORM,
    SessionVideoORM,
    SessionStatsORM,
    SessionManeuverORM,
    SessionLegORM,
    SessionAnalysisORM,
)
from .ingest import ImportORM, SessionUploadORM, SessionStreamORM
from .wind import WindStationORM, WindObservationORM, WindEstimateORM

__all__ = [
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
    "BoatClassORM",
    "BoatORM",
    "UserBoatORM",
    "BoatPhotoORM",
    "PolarPointORM",
    "DeviceTypeORM",
    "DeviceORM",
    "RegattaORM",
    "RaceDayORM",
    "RaceORM",
    "ResultORM",
    "ActivityORM",
    "MarkORM",
    "SessionORM",
    "SessionCrewORM",
    "SessionPhotoORM",
    "SessionVideoORM",
    "SessionStatsORM",
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
