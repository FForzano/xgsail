"""SQLAlchemy ORM models (Postgres mapping of the domain objects).

One module per aggregate. Importing this package registers every table on
``Base.metadata`` so ``init_db()`` / ``create_all`` sees them.
"""

from .regatta import RegattaORM
from .raceday import RaceDayORM
from .race import RaceORM, MarkORM, RaceBoatORM, RaceResultORM
from .boat import BoatORM, BoatMemberORM
from .group import GroupORM, GroupMemberORM
from .device import DeviceORM, DeviceAssignmentORM
from .session import SessionORM, SessionCrewORM
from .rbac import (
    UserORM,
    ClubORM,
    ClubMemberORM,
    AuthRefreshTokenORM,
    RoleORM,
    PermissionORM,
    RolePermissionORM,
    UserRoleORM,
)

__all__ = [
    "RegattaORM",
    "RaceDayORM",
    "RaceORM",
    "MarkORM",
    "RaceBoatORM",
    "RaceResultORM",
    "BoatORM",
    "BoatMemberORM",
    "GroupORM",
    "GroupMemberORM",
    "DeviceORM",
    "DeviceAssignmentORM",
    "SessionORM",
    "SessionCrewORM",
    "UserORM",
    "ClubORM",
    "ClubMemberORM",
    "AuthRefreshTokenORM",
    "RoleORM",
    "PermissionORM",
    "RolePermissionORM",
    "UserRoleORM",
]
