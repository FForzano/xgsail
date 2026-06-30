"""Storage-agnostic domain objects for SailFrames.

These Pydantic models are the canonical in-memory representation of each
entity. Endpoints and business logic work with *these* objects regardless of
whether persistence is object storage (JSON) or Postgres — that is what keeps
the logic single across backends. The repository layer
(``web/api/repositories``) converts between these and the chosen backend.

One module per aggregate; this package just re-exports them.
"""

from .base import DomainModel
from .regatta import Regatta
from .raceday import RaceDay
from .race import Race, Mark, RaceBoat, StartFinishLine, RaceResult
from .boat import Boat
from .session import Session
from .user import User

__all__ = [
    "DomainModel",
    "Regatta",
    "RaceDay",
    "Race",
    "Mark",
    "RaceBoat",
    "StartFinishLine",
    "RaceResult",
    "Boat",
    "Session",
    "User",
]
