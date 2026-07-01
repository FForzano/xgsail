"""SQL (Postgres) repository backend.

``build_sql_repos`` initialises the schema (``create_all``) and wires the
per-entity SQL repositories. Sessions retain access to the blob store for
manifest backfill (the processing pipeline writes manifests there).
"""

from ...db import get_sessionmaker, init_db
from ...storage import BlobStore
from ..base import Repositories
from .regatta_repo import SqlRegattaRepo
from .raceday_repo import SqlRaceDayRepo
from .race_repo import SqlRaceRepo
from .boat_repo import SqlBoatRepo
from .session_repo import SqlSessionRepo
from .user_repo import SqlUserRepo
from .auth_token_repo import SqlAuthTokenRepo
from .club_repo import SqlClubRepo
from .group_repo import SqlGroupRepo
from .device_repo import SqlDeviceRepo


def build_sql_repos(blob: BlobStore, data_prefix: str) -> Repositories:
    init_db()
    sf = get_sessionmaker()
    return Repositories(
        regattas=SqlRegattaRepo(sf),
        racedays=SqlRaceDayRepo(sf),
        races=SqlRaceRepo(sf),
        boats=SqlBoatRepo(sf),
        sessions=SqlSessionRepo(sf, blob, data_prefix),
        users=SqlUserRepo(sf),
        auth_tokens=SqlAuthTokenRepo(sf),
        clubs=SqlClubRepo(sf),
        groups=SqlGroupRepo(sf),
        devices=SqlDeviceRepo(sf),
    )


__all__ = [
    "build_sql_repos",
    "SqlRegattaRepo",
    "SqlRaceDayRepo",
    "SqlRaceRepo",
    "SqlBoatRepo",
    "SqlSessionRepo",
    "SqlUserRepo",
    "SqlAuthTokenRepo",
    "SqlClubRepo",
    "SqlGroupRepo",
    "SqlDeviceRepo",
]
