"""Manual import request DTOs (docs/api-project.md §3)."""

import uuid
from typing import Optional

from pydantic import AwareDatetime, BaseModel


class ImportCreateModel(BaseModel):
    original_filename: str


class ImportCompleteModel(BaseModel):
    boat_id: uuid.UUID
    activity_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    subject_type: str = "boat"  # boat | crew_member
    subject_user_id: Optional[uuid.UUID] = None
    started_at: Optional[AwareDatetime] = None  # fallback when the file has no timestamps
