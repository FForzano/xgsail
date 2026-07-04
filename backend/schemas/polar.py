"""Polar curve request DTOs — a curve is replaced wholesale per target."""

import uuid
from typing import Optional

from pydantic import BaseModel


class PolarPointModel(BaseModel):
    twa_deg: float
    tws_kts: float
    speed_kts: float
    vmg_kts: Optional[float] = None
    sample_count: Optional[int] = None


class PolarUpsertModel(BaseModel):
    # Exactly one target (mirrors the DB CHECK) — enforced by the router.
    class_id: Optional[uuid.UUID] = None
    boat_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    source: str = "reference"  # reference | empirical
    points: list[PolarPointModel]
