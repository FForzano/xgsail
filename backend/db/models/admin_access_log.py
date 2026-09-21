"""``admin_access_log``: which superadmin looked at which user's data.

The instance operator can read any registered user's profile, boats,
activities and sessions for diagnostics (``backend/routers/admin.py``). That is
a deliberately broad read, so every one of those endpoints leaves exactly one
row here — accountability for an access the subject cannot see happening.

Write-only from the application's point of view: nothing updates or deletes a
row, and the only reader is the operator-facing ``GET /api/admin/access-log``.
"""

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, UUIDPKMixin, enum_check

ADMIN_ACCESS_ACTIONS = (
    "user.detail",
    "user.boats",
    "user.activities",
    "user.sessions",
)


class AdminAccessLogORM(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "admin_access_log"
    __table_args__ = (
        # The listing is "newest first, optionally one subject" — the filter is
        # indexed by the column below, the ordering by this.
        Index("ix_admin_access_log_created_at", "created_at"),
        enum_check("action", ADMIN_ACCESS_ACTIONS),
    )

    # SET NULL, not CASCADE: the point of the row is that the access happened,
    # and deleting either party must not erase that evidence. RESTRICT would
    # preserve more (the ids) but would make the audit table veto a user's
    # erasure, which is the wrong trade for a log nobody is allowed to edit.
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
