"""Session request DTOs: sessions + crew."""

import uuid
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel


class SessionWriteModel(BaseModel):
    activity_id: Optional[uuid.UUID] = None  # required on create
    boat_id: Optional[uuid.UUID] = None  # required on create
    started_at: Optional[AwareDatetime] = None
    ended_at: Optional[AwareDatetime] = None


class SessionCrewModel(BaseModel):
    user_id: uuid.UUID
    sailing_role: Literal["skipper", "crew", "guest"] = "crew"


class ManeuverCorrectionModel(BaseModel):
    # Mirrors backend/db/models/session.py::MANEUVER_TYPES — kept as a
    # literal (not imported) since schemas stay dependency-free of db/models.
    maneuver_type: Literal["tack", "gybe", "course_change"]


class ManeuverRejectionModel(BaseModel):
    rejected: bool


class ManeuverCreateModel(BaseModel):
    maneuver_type: Literal["tack", "gybe", "course_change"]
    start_time: float
    end_time: float


class SessionTrimModel(BaseModel):
    """Both bounds are required (not exclude_unset) so the client always
    states its intent explicitly — including `null` to clear an existing
    trim — rather than relying on omission."""
    trim_start_time: Optional[float] = None
    trim_end_time: Optional[float] = None


class SessionAttachModel(BaseModel):
    activity_id: uuid.UUID


class SessionNotesModel(BaseModel):
    notes: Optional[str] = None
    notes_shared: bool = False


class PhysioSharingModel(BaseModel):
    """Whether this crew member lets the session's crew/boat managers see their
    physiological data. Only the subject may send it — see
    ``auth.session_physio_visible_to``."""
    shared: bool


class NavSourceModel(BaseModel):
    """Which upload's GPS becomes the session's navigation track (see
    ``services/nav_source.py``). Changing it re-runs the analysis, because
    polars/VMG/maneuvers were computed against the previous track."""
    session_upload_id: uuid.UUID
