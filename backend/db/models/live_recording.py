"""``live_recordings`` — who is recording right now, per boat.

Presence, not data: a row says "this user has a recording running on this
boat", nothing more. Nothing here creates or reserves a ``sessions`` row, so a
recording that is abandoned mid-outing leaves no empty session behind — the
session is still born the usual way, when the track is uploaded
(``services/ingestion.py::find_or_create_session``).

One row per (boat, person), updated in place by the heartbeat, and deleted
when the recording stops. The table is therefore bounded by how many people
record on how many boats, not by how many recordings have ever been made.

Liveness is decided **at read time** from ``last_seen_at`` rather than by a
cleanup job: the phone heartbeats while it records, and an app that was killed
mid-outing simply stops. Nothing has to notice the death, and there is no
scheduled task to add to the self-hosted stack. The price is a ghost row that
keeps advertising for up to ``LIVE_STALE_AFTER`` — the window is generous on
purpose, because the heartbeat comes from a phone that is locked and
backgrounded for most of an outing.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDPKMixin

# How long a row keeps counting as live without a heartbeat.
LIVE_STALE_AFTER = timedelta(minutes=20)
# Rows nothing will ever refresh again, dropped opportunistically on write.
LIVE_PRUNE_AFTER = timedelta(hours=24)


class LiveRecordingORM(UUIDPKMixin, Base):
    __tablename__ = "live_recordings"
    __table_args__ = (UniqueConstraint("boat_id", "user_id"),)

    boat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("boats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # NULL = standalone recording ("uscita singola"), same convention as
    # RecordingMeta.activityId in services/nativeRecording.ts. Prefills the
    # activity for whoever joins from the banner.
    activity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
    # The phone's own recording id (RecordingMeta.id). Only job: tell a
    # heartbeat for the recording already announced from a brand-new one, so
    # started_at is preserved in the first case and reset in the second.
    client_recording_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
