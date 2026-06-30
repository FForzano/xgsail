"""API request/response DTOs (Pydantic) for the SailFrames HTTP layer.

These are the *wire* shapes accepted/returned by endpoints, kept separate from
the storage-agnostic domain models in ``web/api/domain``. Endpoints translate
between the two.
"""

from .regatta import RegattaCreateModel, RegattaUpdateModel
from .raceday import RaceDayCreateModel, RaceDayUpdateModel
from .race import (
    StartFinishLineModel,
    MarkModel,
    RaceBoatModel,
    RaceCreateModel,
    RaceUpdateModel,
)

__all__ = [
    "RegattaCreateModel",
    "RegattaUpdateModel",
    "RaceDayCreateModel",
    "RaceDayUpdateModel",
    "StartFinishLineModel",
    "MarkModel",
    "RaceBoatModel",
    "RaceCreateModel",
    "RaceUpdateModel",
]
