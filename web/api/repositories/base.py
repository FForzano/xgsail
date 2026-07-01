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

    # Standing-crew membership. Object backend nests these inside the boat
    # record; SQL uses the ``boat_members`` table. Both no-op on unknown boat.
    @abstractmethod
    def add_member(self, boat_id: str, member: domain.BoatMember) -> bool: ...
    @abstractmethod
    def remove_member(self, boat_id: str, user_id: int) -> bool: ...
    @abstractmethod
    def set_member_role(self, boat_id: str, user_id: int, role: str) -> bool: ...
    @abstractmethod
    def list_members(self, boat_id: str) -> "list[domain.BoatMember]": ...
    @abstractmethod
    def is_member(self, boat_id: str, user_id: int, roles: "Optional[list[str]]" = None) -> bool: ...


class SessionRepo(ABC):
    @abstractmethod
    def list(self) -> list[domain.Session]: ...
    @abstractmethod
    def get(self, device_id: str, date: str) -> Optional[domain.Session]: ...

    def upsert(self, session: domain.Session) -> domain.Session:
        """Persist a session record to the deploy's authoritative store: the
        blob ``manifest.json`` (object backend) or the ``sessions`` row + crew
        (SQL backend). Used by the ingest boat-snapshot hook and the crew-edit
        endpoint. The default is a no-op; both concrete backends override it."""
        return session


class UserRepo(ABC):
    """Identity store. Password hashes never leave the repo on a ``User``
    domain object — they are read only via ``get_password_hash_by_email`` for
    login and written on ``create``."""

    @abstractmethod
    def list(self) -> list[domain.User]: ...
    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[domain.User]: ...
    @abstractmethod
    def get_by_email(self, email: str) -> Optional[domain.User]: ...
    @abstractmethod
    def get_password_hash_by_email(self, email: str) -> Optional[str]: ...
    @abstractmethod
    def create(self, user: domain.User, password_hash: Optional[str]) -> domain.User: ...


class AuthTokenRepo(ABC):
    """Refresh-token store for rotation + reuse detection."""

    @abstractmethod
    def create(self, token: domain.AuthRefreshToken) -> domain.AuthRefreshToken: ...
    @abstractmethod
    def get_by_hash(self, token_hash: str) -> Optional[domain.AuthRefreshToken]: ...
    @abstractmethod
    def revoke(self, token_id: int, revoked_at: str) -> None: ...
    @abstractmethod
    def revoke_family(self, family_id: str, revoked_at: str) -> None: ...


class ClubRepo(ABC):
    @abstractmethod
    def list(self) -> list[domain.Club]: ...
    @abstractmethod
    def get(self, club_id: int) -> Optional[domain.Club]: ...
    @abstractmethod
    def save(self, club: domain.Club) -> domain.Club: ...
    @abstractmethod
    def add_member(self, club_id: int, member: domain.ClubMember) -> bool: ...
    @abstractmethod
    def set_member_status(self, club_id: int, user_id: int, status: str) -> bool: ...
    @abstractmethod
    def is_active_member(self, club_id: int, user_id: int) -> bool: ...


class GroupRepo(ABC):
    """Free social groups (independent of clubs/boats). Membership carries a
    ``role`` (admin|member) as well as a ``status`` (invited|active); ``admin``
    membership — not a single owner column — grants management rights."""

    @abstractmethod
    def list(self) -> list[domain.Group]: ...
    @abstractmethod
    def get(self, group_id: int) -> Optional[domain.Group]: ...
    @abstractmethod
    def save(self, group: domain.Group) -> domain.Group: ...
    @abstractmethod
    def add_member(self, group_id: int, member: domain.GroupMember) -> bool: ...
    @abstractmethod
    def set_member_status(self, group_id: int, user_id: int, status: str) -> bool: ...
    @abstractmethod
    def set_member_role(self, group_id: int, user_id: int, role: str) -> bool: ...
    @abstractmethod
    def is_member(self, group_id: int, user_id: int) -> bool: ...


class DeviceRepo(ABC):
    """Tracker registry + attribution windows. ``add_assignment`` rejects
    overlapping windows for a device (raises ``ValueError`` → 409 at the
    router). ``resolve_boat`` applies: covering window → default_boat_id →
    None."""

    @abstractmethod
    def list(self) -> list[domain.Device]: ...
    @abstractmethod
    def get(self, device_id: str) -> Optional[domain.Device]: ...
    @abstractmethod
    def register(self, device: domain.Device) -> domain.Device: ...
    @abstractmethod
    def add_assignment(self, assignment: domain.DeviceAssignment) -> domain.DeviceAssignment: ...
    @abstractmethod
    def list_assignments(self, device_id: str) -> "list[domain.DeviceAssignment]": ...
    @abstractmethod
    def resolve_boat(self, device_id: str, at_iso: str) -> Optional[str]: ...
    @abstractmethod
    def touch_last_seen(self, device_id: str, at_iso: str) -> bool: ...


class Repositories:
    """Facade bundling one repo per aggregate."""

    def __init__(
        self,
        regattas: RegattaRepo,
        racedays: RaceDayRepo,
        races: RaceRepo,
        boats: BoatRepo,
        sessions: SessionRepo,
        users: UserRepo,
        auth_tokens: AuthTokenRepo,
        clubs: ClubRepo,
        groups: GroupRepo,
        devices: DeviceRepo,
    ):
        self.regattas = regattas
        self.racedays = racedays
        self.races = races
        self.boats = boats
        self.sessions = sessions
        self.users = users
        self.auth_tokens = auth_tokens
        self.clubs = clubs
        self.groups = groups
        self.devices = devices
