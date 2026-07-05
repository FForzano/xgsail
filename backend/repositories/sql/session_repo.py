"""SQL session repository: ``sessions`` + crew/photos/videos/stats children.

``find_for_boat_window``/``extend_window`` implement the find-or-create logic
shared by device uploads, manual imports, and the legacy E1 callback — the
same 10-minute merge gap the processing worker uses for its folders, so DB
sessions and worker output converge. ``rollup_status`` derives the session
status from its ``session_uploads``.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from ...db.models import (
    SessionCrewORM,
    SessionORM,
    SessionPhotoORM,
    SessionStatsORM,
    SessionUploadORM,
    SessionVideoORM,
)

_FIELDS = ("activity_id", "boat_id", "started_at", "ended_at", "status")
_STATS_FIELDS = ("distance_m", "avg_speed_kts", "max_speed_kts", "duration_s",
                 "avg_polar_pct", "max_polar_pct", "computed_at")


class SqlSessionRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self, *, activity_id: Optional[uuid.UUID] = None,
             boat_id: Optional[uuid.UUID] = None) -> "list[SessionORM]":
        with self.Session() as s:
            q = select(SessionORM)
            if activity_id is not None:
                q = q.where(SessionORM.activity_id == activity_id)
            if boat_id is not None:
                q = q.where(SessionORM.boat_id == boat_id)
            return list(s.scalars(q).all())

    def list_for_user(self, user_id: uuid.UUID) -> "list[SessionORM]":
        """Sessions the user took part in: crew rows plus any session of a boat
        they are a member of (``?mine=true``)."""
        from ...db.models import UserBoatORM

        with self.Session() as s:
            boat_ids = select(UserBoatORM.boat_id).where(UserBoatORM.user_id == user_id)
            crew_ids = select(SessionCrewORM.session_id).where(
                SessionCrewORM.user_id == user_id
            )
            q = select(SessionORM).where(
                SessionORM.boat_id.in_(boat_ids) | SessionORM.id.in_(crew_ids)
            ).order_by(SessionORM.started_at.desc().nulls_last())
            return list(s.scalars(q).all())

    def get(self, session_id: uuid.UUID) -> Optional[SessionORM]:
        with self.Session() as s:
            return s.get(SessionORM, session_id)

    def create(self, data: dict) -> SessionORM:
        with self.Session() as s:
            orm = SessionORM(**{k: data.get(k) for k in _FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, session_id: uuid.UUID, changes: dict) -> Optional[SessionORM]:
        with self.Session() as s:
            orm = s.get(SessionORM, session_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(session_id)

    def delete(self, session_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(SessionORM, session_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    # --- find-or-create support ---

    def find_for_boat_window(self, boat_id: uuid.UUID, started_at: datetime,
                             ended_at: Optional[datetime] = None,
                             gap_minutes: int = 10) -> Optional[SessionORM]:
        """A session of this boat whose window overlaps (or comes within
        ``gap_minutes`` of) [started_at, ended_at]. Mirrors the worker's
        SESSION_MERGE_GAP_MINUTES so DB sessions align with merged folders."""
        gap = timedelta(minutes=gap_minutes)
        new_start = started_at
        new_end = ended_at or started_at
        with self.Session() as s:
            candidates = s.scalars(
                select(SessionORM).where(SessionORM.boat_id == boat_id)
            ).all()
            for sess in candidates:
                if sess.started_at is None:
                    continue
                sess_start = sess.started_at
                sess_end = sess.ended_at or sess.started_at
                if sess_start - gap <= new_end and sess_end + gap >= new_start:
                    return sess
        return None

    def extend_window(self, session_id: uuid.UUID, started_at: Optional[datetime],
                      ended_at: Optional[datetime]) -> None:
        """Widen the session bounds monotonically (min start, max end)."""
        with self.Session() as s:
            orm = s.get(SessionORM, session_id)
            if orm is None:
                return
            if started_at is not None and (orm.started_at is None or started_at < orm.started_at):
                orm.started_at = started_at
            if ended_at is not None and (orm.ended_at is None or ended_at > orm.ended_at):
                orm.ended_at = ended_at
            s.commit()

    def rollup_status(self, session_id: uuid.UUID) -> Optional[str]:
        """Derive sessions.status from the linked session_uploads and persist.

        In-flight states dominate; ``failed`` only when nothing succeeded."""
        with self.Session() as s:
            orm = s.get(SessionORM, session_id)
            if orm is None:
                return None
            statuses = [
                u.status for u in s.scalars(
                    select(SessionUploadORM).where(SessionUploadORM.session_id == session_id)
                )
            ]
            if not statuses:
                new_status = "pending"
            elif "processing" in statuses:
                new_status = "processing"
            elif "pending" in statuses:
                new_status = "pending" if "processed" not in statuses else "processing"
            elif "processed" in statuses:
                new_status = "processed"
            else:
                new_status = "failed"
            orm.status = new_status
            s.commit()
            return new_status

    # --- crew ---

    def list_crew(self, session_id: uuid.UUID) -> "list[SessionCrewORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(SessionCrewORM).where(SessionCrewORM.session_id == session_id)
            ).all())

    def add_crew(self, session_id: uuid.UUID, *, user_id: uuid.UUID,
                 sailing_role: str = "crew") -> bool:
        with self.Session() as s:
            exists = s.scalars(
                select(SessionCrewORM).where(
                    SessionCrewORM.session_id == session_id,
                    SessionCrewORM.user_id == user_id,
                )
            ).first()
            if exists is not None:
                return False
            s.add(SessionCrewORM(session_id=session_id, user_id=user_id,
                                 sailing_role=sailing_role))
            s.commit()
            return True

    def remove_crew(self, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.scalars(
                select(SessionCrewORM).where(
                    SessionCrewORM.session_id == session_id,
                    SessionCrewORM.user_id == user_id,
                )
            ).first()
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def is_crew(self, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        with self.Session() as s:
            return s.scalars(
                select(SessionCrewORM).where(
                    SessionCrewORM.session_id == session_id,
                    SessionCrewORM.user_id == user_id,
                )
            ).first() is not None

    # --- photos / videos ---

    def list_photos(self, session_id: uuid.UUID) -> "list[SessionPhotoORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(SessionPhotoORM).where(SessionPhotoORM.session_id == session_id)
            ).all())

    def add_photo(self, session_id: uuid.UUID, *, image_id: uuid.UUID,
                  created_by: Optional[uuid.UUID]) -> SessionPhotoORM:
        with self.Session() as s:
            orm = SessionPhotoORM(session_id=session_id, image_id=image_id,
                                  created_by=created_by)
            s.add(orm)
            s.commit()
            s.refresh(orm)
            s.expunge(orm)
            return orm

    def get_photo(self, session_id: uuid.UUID, image_id: uuid.UUID) -> Optional[SessionPhotoORM]:
        with self.Session() as s:
            return s.scalars(
                select(SessionPhotoORM).where(
                    SessionPhotoORM.session_id == session_id,
                    SessionPhotoORM.image_id == image_id,
                )
            ).first()

    def remove_photo(self, session_id: uuid.UUID, image_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.scalars(
                select(SessionPhotoORM).where(
                    SessionPhotoORM.session_id == session_id,
                    SessionPhotoORM.image_id == image_id,
                )
            ).first()
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def list_videos(self, session_id: uuid.UUID) -> "list[SessionVideoORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(SessionVideoORM).where(SessionVideoORM.session_id == session_id)
            ).all())

    def add_video(self, session_id: uuid.UUID, *, file_id: uuid.UUID,
                  created_by: Optional[uuid.UUID]) -> SessionVideoORM:
        with self.Session() as s:
            orm = SessionVideoORM(session_id=session_id, file_id=file_id,
                                  created_by=created_by)
            s.add(orm)
            s.commit()
            s.refresh(orm)
            s.expunge(orm)
            return orm

    def get_video(self, session_id: uuid.UUID, file_id: uuid.UUID) -> Optional[SessionVideoORM]:
        with self.Session() as s:
            return s.scalars(
                select(SessionVideoORM).where(
                    SessionVideoORM.session_id == session_id,
                    SessionVideoORM.file_id == file_id,
                )
            ).first()

    def remove_video(self, session_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.scalars(
                select(SessionVideoORM).where(
                    SessionVideoORM.session_id == session_id,
                    SessionVideoORM.file_id == file_id,
                )
            ).first()
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    # --- stats ---

    def get_stats(self, session_id: uuid.UUID) -> Optional[SessionStatsORM]:
        with self.Session() as s:
            return s.get(SessionStatsORM, session_id)

    def upsert_stats(self, session_id: uuid.UUID, data: dict) -> SessionStatsORM:
        with self.Session() as s:
            orm = s.get(SessionStatsORM, session_id)
            if orm is None:
                orm = SessionStatsORM(session_id=session_id)
                s.add(orm)
            for k, v in data.items():
                if k in _STATS_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get_stats(session_id)
