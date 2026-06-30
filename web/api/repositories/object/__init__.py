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


def build_object_repos(blob: BlobStore, data_prefix: str) -> Repositories:
    return Repositories(
        regattas=ObjectRegattaRepo(blob),
        racedays=ObjectRaceDayRepo(blob),
        races=ObjectRaceRepo(blob),
        boats=ObjectBoatRepo(blob, data_prefix),
        sessions=ObjectSessionRepo(blob, data_prefix),
    )


__all__ = [
    "build_object_repos",
    "ObjectRegattaRepo",
    "ObjectRaceDayRepo",
    "ObjectRaceRepo",
    "ObjectBoatRepo",
    "ObjectSessionRepo",
]
