"""SQL (Postgres) repository backend.

``build_sql_repos`` initialises the schema (Alembic ``upgrade head``) and wires
the per-aggregate SQL repositories. ``blob``/``data_prefix`` are accepted for
factory-signature stability (repos are DB-only; blob access lives in routers/
services via ``get_blob_store``).
"""

from ...db import get_sessionmaker, init_db
from ...storage import BlobStore
from ..base import Repositories
from .user_repo import SqlUserRepo
from .auth_token_repo import SqlAuthTokenRepo
from .club_repo import SqlClubRepo
from .group_repo import SqlGroupRepo
from .boat_repo import SqlBoatRepo
from .device_repo import SqlDeviceRepo
from .activity_repo import SqlActivityRepo
from .session_repo import SqlSessionRepo
from .ingest_repo import SqlIngestRepo
from .race_repo import SqlRegattaRepo, SqlRaceDayRepo, SqlRaceRepo
from .media_repo import SqlMediaRepo
from .wind_repo import SqlWindRepo
from .polar_repo import SqlPolarRepo
from .rbac_repo import SqlRbacRepo
from .app_config_repo import SqlAppConfigRepo
from .post_repo import SqlPostRepo


def build_sql_repos(blob: BlobStore, data_prefix: str) -> Repositories:
    init_db()
    sf = get_sessionmaker()
    return Repositories(
        users=SqlUserRepo(sf),
        auth_tokens=SqlAuthTokenRepo(sf),
        clubs=SqlClubRepo(sf),
        groups=SqlGroupRepo(sf),
        boats=SqlBoatRepo(sf),
        devices=SqlDeviceRepo(sf),
        activities=SqlActivityRepo(sf),
        sessions=SqlSessionRepo(sf),
        ingest=SqlIngestRepo(sf),
        regattas=SqlRegattaRepo(sf),
        racedays=SqlRaceDayRepo(sf),
        races=SqlRaceRepo(sf),
        media=SqlMediaRepo(sf),
        wind=SqlWindRepo(sf),
        polars=SqlPolarRepo(sf),
        rbac=SqlRbacRepo(sf),
        app_config=SqlAppConfigRepo(sf),
        posts=SqlPostRepo(sf),
    )


__all__ = [
    "build_sql_repos",
    "SqlUserRepo",
    "SqlAuthTokenRepo",
    "SqlClubRepo",
    "SqlGroupRepo",
    "SqlBoatRepo",
    "SqlDeviceRepo",
    "SqlActivityRepo",
    "SqlSessionRepo",
    "SqlIngestRepo",
    "SqlRegattaRepo",
    "SqlRaceDayRepo",
    "SqlRaceRepo",
    "SqlMediaRepo",
    "SqlWindRepo",
    "SqlPolarRepo",
    "SqlRbacRepo",
    "SqlAppConfigRepo",
    "SqlPostRepo",
]
