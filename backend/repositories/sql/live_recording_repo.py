"""SQL live-recording repository — presence rows for in-progress recordings.

Liveness is a read-time predicate over ``last_seen_at`` (see
``db/models/live_recording.py``), so every listing here applies the staleness
cutoff itself rather than assuming somebody pruned the table.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select

from ...db.models import LiveRecordingORM
from ...db.models.live_recording import LIVE_PRUNE_AFTER, LIVE_STALE_AFTER


class SqlLiveRecordingRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def upsert(self, *, boat_id: uuid.UUID, user_id: uuid.UUID,
               activity_id: Optional[uuid.UUID] = None,
               client_recording_id: Optional[str] = None,
               now: Optional[datetime] = None) -> LiveRecordingORM:
        """Announce a recording, or keep an announced one alive.

        Start and heartbeat are the same write: ``started_at`` is preserved
        while ``client_recording_id`` keeps naming the recording already
        announced, and reset when a different one takes its place. That makes
        the call idempotent, so the app can retry it whenever connectivity
        returns without tracking whether the first attempt got through.
        """
        now = now or datetime.now(timezone.utc)
        with self.Session() as s:
            row = s.scalars(
                select(LiveRecordingORM).where(
                    LiveRecordingORM.boat_id == boat_id,
                    LiveRecordingORM.user_id == user_id,
                )
            ).first()
            if row is None:
                row = LiveRecordingORM(
                    boat_id=boat_id, user_id=user_id, activity_id=activity_id,
                    client_recording_id=client_recording_id,
                    started_at=now, last_seen_at=now,
                )
                s.add(row)
            else:
                if client_recording_id != row.client_recording_id:
                    row.client_recording_id = client_recording_id
                    row.started_at = now
                row.activity_id = activity_id
                row.last_seen_at = now
            s.commit()
            s.refresh(row)
            s.expunge(row)
            return row

    def end(self, *, boat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Stop advertising. Deletes rather than tombstoning: nothing reads
        "ended", and a delete retried after a crash is a harmless no-op."""
        with self.Session() as s:
            result = s.execute(
                delete(LiveRecordingORM).where(
                    LiveRecordingORM.boat_id == boat_id,
                    LiveRecordingORM.user_id == user_id,
                )
            )
            s.commit()
            return bool(result.rowcount)

    def list_active(self, boat_ids: "list[uuid.UUID]", *,
                    now: Optional[datetime] = None,
                    exclude_user_id: Optional[uuid.UUID] = None,
                    ) -> "list[LiveRecordingORM]":
        if not boat_ids:
            return []
        cutoff = (now or datetime.now(timezone.utc)) - LIVE_STALE_AFTER
        with self.Session() as s:
            q = (
                select(LiveRecordingORM)
                .where(
                    LiveRecordingORM.boat_id.in_(boat_ids),
                    LiveRecordingORM.last_seen_at >= cutoff,
                )
                .order_by(LiveRecordingORM.started_at.desc())
            )
            if exclude_user_id is not None:
                q = q.where(LiveRecordingORM.user_id != exclude_user_id)
            return list(s.scalars(q).all())

    def prune(self, *, now: Optional[datetime] = None,
              older_than: timedelta = LIVE_PRUNE_AFTER) -> int:
        """Drop rows nothing will ever refresh again. Called on write so the
        table stays bounded without a scheduled job."""
        cutoff = (now or datetime.now(timezone.utc)) - older_than
        with self.Session() as s:
            result = s.execute(
                delete(LiveRecordingORM).where(LiveRecordingORM.last_seen_at < cutoff)
            )
            s.commit()
            return int(result.rowcount or 0)
