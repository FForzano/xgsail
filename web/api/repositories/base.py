"""Repository interfaces for SailFrames structured ("small") data.

Each repository persists one aggregate and speaks **domain objects**
(``web/api/domain``), never dicts or ORM rows, so endpoints are identical
across backends. Two implementations exist:

- ``ObjectMetadataRepo`` (object_repo.py) — JSON in the blob store, preserving
  today's on-disk index format (so the cloud/self-hosted object mode is
  unchanged).
- ``SqlMetadataRepo`` (sql_repo.py) — SQLAlchemy + Postgres.

``get_repos()`` (``__init__.py``) builds the right ``Repositories`` facade from
``SAILFRAMES_METADATA_BACKEND``.

Note on listing: where the current code keeps a lightweight summary index
(races), the repo exposes ``list_summaries()`` returning the same summary dicts
the API already emits, alongside ``get()`` for the full object — this keeps the
wire responses byte-identical without N per-item reads.
"""

from abc import ABC, abstractmethod
from typing import Optional

from .. import domain


class RegattaRepo(ABC):
    @abstractmethod
    def list(self) -> list[domain.Regatta]: ...
    @abstractmethod
    def get(self, regatta_id: str) -> Optional[domain.Regatta]: ...
    @abstractmethod
    def save(self, regatta: domain.Regatta) -> domain.Regatta: ...
    @abstractmethod
    def delete(self, regatta_id: str) -> bool: ...


class RaceDayRepo(ABC):
    @abstractmethod
    def list(self) -> list[domain.RaceDay]: ...
    @abstractmethod
    def get(self, raceday_id: str) -> Optional[domain.RaceDay]: ...
    @abstractmethod
    def save(self, raceday: domain.RaceDay) -> domain.RaceDay: ...
    @abstractmethod
    def delete(self, raceday_id: str) -> bool: ...


class RaceRepo(ABC):
    @abstractmethod
    def list_summaries(
        self,
        *,
        regatta_id: Optional[str] = None,
        date: Optional[str] = None,
        raceday_id: Optional[str] = None,
    ) -> list[dict]: ...
    @abstractmethod
    def get(self, race_id: str) -> Optional[domain.Race]: ...
    @abstractmethod
    def save(self, race: domain.Race) -> domain.Race: ...
    @abstractmethod
    def delete(self, race_id: str) -> bool: ...


class BoatRepo(ABC):
    @abstractmethod
    def list(self) -> list[domain.Boat]: ...
    @abstractmethod
    def get(self, boat_id: str) -> Optional[domain.Boat]: ...
    @abstractmethod
    def save(self, boat: domain.Boat) -> domain.Boat: ...
    @abstractmethod
    def delete(self, boat_id: str) -> bool: ...


class SessionRepo(ABC):
    @abstractmethod
    def list(self) -> list[domain.Session]: ...
    @abstractmethod
    def get(self, device_id: str, date: str) -> Optional[domain.Session]: ...

    def upsert(self, session: domain.Session) -> domain.Session:
        """Persist a session record. No-op for backends where the blob
        manifest is the source of truth (object); the SQL backend writes a row.
        Used by the ingest pipeline to keep the table populated."""
        return session


class Repositories:
    """Facade bundling one repo per aggregate."""

    def __init__(
        self,
        regattas: RegattaRepo,
        racedays: RaceDayRepo,
        races: RaceRepo,
        boats: BoatRepo,
        sessions: SessionRepo,
    ):
        self.regattas = regattas
        self.racedays = racedays
        self.races = races
        self.boats = boats
        self.sessions = sessions
