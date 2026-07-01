"""Session request DTOs (Phase 5 crew/privacy edit)."""

from typing import Optional

from pydantic import BaseModel


class SessionCrewSlotModel(BaseModel):
    user_id: Optional[int] = None
    guest_name: Optional[str] = None
    boat_role: Optional[str] = None


class SessionCrewModel(BaseModel):
    """Edit a session's crew (and optionally claim its boat/visibility).

    ``crew`` replaces the session's crew wholesale. Each slot must set exactly
    one of ``user_id`` / ``guest_name`` (a registered user or a guest)."""

    crew: list[SessionCrewSlotModel] = []
    boat_id: Optional[str] = None
    visibility: Optional[str] = None  # private | group | club | public
    club_id: Optional[int] = None
    group_id: Optional[int] = None
