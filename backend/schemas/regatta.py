"""Regatta request DTOs."""

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from ..richtext import RichTextBasic


class RegattaEntryWriteModel(BaseModel):
    """Organizer putting a boat on the start list — either a real boat
    (``boat_id``) or a manual/paper entry (``boat_name``, optionally
    ``sail_number``) for a boat with no XGSail account yet."""

    boat_id: Optional[uuid.UUID] = None
    boat_name: Optional[str] = None
    sail_number: Optional[str] = None
    division_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def _require_boat_id_or_name(self) -> "RegattaEntryWriteModel":
        # Mirrors the DB CHECK (boat_id IS NOT NULL OR boat_name IS NOT NULL).
        if self.boat_id is None and not (self.boat_name and self.boat_name.strip()):
            raise ValueError("boat_id or boat_name is required")
        return self


class RegattaEntryLinkModel(BaseModel):
    """Organizer matching a manual entry to a real boat."""

    boat_id: uuid.UUID


class RegattaEntryDivisionModel(BaseModel):
    """Organizer (re)assigning an entry's division. ``division_id`` explicitly
    ``null`` unassigns the entry from any division."""

    division_id: Optional[uuid.UUID] = None


class RegattaJoinModel(BaseModel):
    """Sailor self-entering with the share code. ``boat_id`` must be a boat
    they own/administer — the code grants entry, not the right to enter
    someone else's boat."""

    code: str = Field(min_length=1, max_length=32)
    boat_id: uuid.UUID
    division_id: Optional[uuid.UUID] = None


class RegattaWriteModel(BaseModel):
    name: Optional[str] = None  # required on create, enforced by the router
    description: RichTextBasic = None
    club_id: Optional[uuid.UUID] = None  # required on create
    class_id: Optional[uuid.UUID] = None
    scoring_system: Optional[str] = None  # low_point | bonus_point | custom
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None  # scheduled | active | completed


class RegattaDivisionWriteModel(BaseModel):
    """Organizer defining a scoring division (e.g. "Catamarani", "Derive") —
    a free-form category with its own ranking within the regatta."""

    name: str
    sort_order: int = 0
    laps: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _require_non_blank_name(self) -> "RegattaDivisionWriteModel":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("name is required")
        return self


class RegattaDivisionPatchModel(BaseModel):
    """Partial update to a division — used with ``exclude_unset``."""

    name: Optional[str] = None
    sort_order: Optional[int] = None
    laps: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _reject_blank_name(self) -> "RegattaDivisionPatchModel":
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("name cannot be blank")
        return self


class OfficialStandingsRowModel(BaseModel):
    """One row of official standings: a boat and its official position/score."""

    boat_id: uuid.UUID
    position: int
    score: Optional[float] = None
    status: Optional[str] = None  # dnf, dns, dsq, etc
    division_id: Optional[uuid.UUID] = None


class OfficialStandingsUploadModel(BaseModel):
    """Upload official standings to replace computed standings for a regatta."""

    standings: list[OfficialStandingsRowModel]
