"""Race-day request DTOs."""

import uuid
from datetime import date as date_t
from typing import Optional

from pydantic import BaseModel


class RaceDayWriteModel(BaseModel):
    regatta_id: Optional[uuid.UUID] = None  # NULL = free race day (superadmin/global only)
    date: Optional[date_t] = None  # required on create
    notes: Optional[str] = None
