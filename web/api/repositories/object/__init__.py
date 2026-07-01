"""Object-storage repository backend: structured data as JSON in the blob
store, preserving the historical on-disk layout (so the default ``object``
metadata backend is behaviourally identical to the pre-refactor code).
"""

from ...storage import BlobStore
from ..base import Repositories
from .regatta_repo import ObjectRegattaRepo
from .raceday_repo import ObjectRaceDayRepo
from .race_repo import ObjectRaceRepo
from .boat_repo import ObjectBoatRepo
from .session_repo import ObjectSessionRepo
from .user_repo import ObjectUserRepo
from .auth_token_repo import ObjectAuthTokenRepo
from .club_repo import ObjectClubRepo
from .group_repo import ObjectGroupRepo
from .device_repo import ObjectDeviceRepo


def build_object_repos(blob: BlobStore, data_prefix: str) -> Repositories:
    return Repositories(
        regattas=ObjectRegattaRepo(blob),
        racedays=ObjectRaceDayRepo(blob),
        races=ObjectRaceRepo(blob),
        boats=ObjectBoatRepo(blob, data_prefix),
        sessions=ObjectSessionRepo(blob, data_prefix),
        users=ObjectUserRepo(blob),
        auth_tokens=ObjectAuthTokenRepo(blob),
        clubs=ObjectClubRepo(blob),
        groups=ObjectGroupRepo(blob),
        devices=ObjectDeviceRepo(blob),
    )


__all__ = [
    "build_object_repos",
    "ObjectRegattaRepo",
    "ObjectRaceDayRepo",
    "ObjectRaceRepo",
    "ObjectBoatRepo",
    "ObjectSessionRepo",
    "ObjectUserRepo",
    "ObjectAuthTokenRepo",
    "ObjectClubRepo",
    "ObjectGroupRepo",
    "ObjectDeviceRepo",
]
