"""Repository factory.

``get_repos()`` returns a process-wide ``Repositories`` facade chosen by
``SAILFRAMES_METADATA_BACKEND``:

- ``object`` (default) -> JSON in the blob store (object_repo.py)
- ``postgres``         -> SQLAlchemy + Postgres (sql_repo.py)

The blob store is always needed (large data is never DB-backed), so the object
backend simply reuses it.
"""

import os

from ..storage import get_blob_store
from .base import (  # noqa: F401
    Repositories,
    RegattaRepo,
    RaceDayRepo,
    RaceRepo,
    BoatRepo,
    SessionRepo,
)

_repos: Repositories | None = None


def select_metadata_backend() -> str:
    return os.environ.get("SAILFRAMES_METADATA_BACKEND", "object").lower()


def build_repos() -> Repositories:
    backend = select_metadata_backend()
    data_prefix = os.environ.get("SAILFRAMES_DATA_PREFIX", "processed")
    if backend == "postgres":
        # Imported lazily so the object backend never requires SQLAlchemy.
        from .sql import build_sql_repos
        return build_sql_repos(get_blob_store(), data_prefix)
    from .object import build_object_repos
    return build_object_repos(get_blob_store(), data_prefix)


def get_repos() -> Repositories:
    global _repos
    if _repos is None:
        _repos = build_repos()
    return _repos


__all__ = ["Repositories", "get_repos", "build_repos", "select_metadata_backend"]
