"""SQL ingestion repository: ``imports`` + ``session_uploads`` + ``session_streams``.

One repo for the whole ingestion aggregate — these tables only mutate through
the ingestion flows (device upload API, manual imports, worker callbacks).
``replace_streams`` is delete+insert so worker callback retries stay idempotent.
"""

import uuid
from typing import Optional

from sqlalchemy import select

from ...db.models import (
    ImportORM,
    SessionPhysioStatsORM,
    SessionStreamORM,
    SessionUploadORM,
)

_UPLOAD_FIELDS = ("session_id", "source_type", "device_id", "import_id",
                  "subject_type", "subject_user_id", "raw_ref",
                  "sequence_number", "is_final", "status")
_STREAM_FIELDS = ("sensor_type", "data_ref", "sample_rate_hz", "row_count",
                  "first_t", "last_t")
_PHYSIO_STAT_FIELDS = ("avg_hr_bpm", "max_hr_bpm", "min_hr_bpm", "total_kcal",
                       "avg_kcal_per_min", "avg_hrv_ms", "avg_resp_brpm",
                       "hr_duration_s", "computed_at")


class SqlIngestRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    # --- imports ---

    def create_import(self, *, uploaded_by: uuid.UUID, original_filename: str,
                      raw_ref: Optional[str] = None) -> ImportORM:
        with self.Session() as s:
            orm = ImportORM(uploaded_by=uploaded_by, original_filename=original_filename,
                            raw_ref=raw_ref, status="pending")
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_import(new_id)

    def get_import(self, import_id: uuid.UUID) -> Optional[ImportORM]:
        with self.Session() as s:
            return s.get(ImportORM, import_id)

    def list_imports(self, uploaded_by: uuid.UUID) -> "list[ImportORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(ImportORM).where(ImportORM.uploaded_by == uploaded_by)
            ).all())

    def update_import(self, import_id: uuid.UUID, changes: dict) -> Optional[ImportORM]:
        allowed = ("raw_ref", "status")
        with self.Session() as s:
            orm = s.get(ImportORM, import_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in allowed:
                    setattr(orm, k, v)
            s.commit()
        return self.get_import(import_id)

    # --- session_uploads ---

    def create_upload(self, data: dict) -> SessionUploadORM:
        with self.Session() as s:
            orm = SessionUploadORM(**{k: data.get(k) for k in _UPLOAD_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_upload(new_id)

    def get_upload(self, upload_id: uuid.UUID) -> Optional[SessionUploadORM]:
        with self.Session() as s:
            return s.get(SessionUploadORM, upload_id)

    def get_upload_by_key(self, session_id: uuid.UUID, device_id: Optional[uuid.UUID],
                          sequence_number: int) -> Optional[SessionUploadORM]:
        """Lookup on the (session, device, sequence) unique key — the
        idempotency handle for device retries and legacy callbacks."""
        with self.Session() as s:
            q = select(SessionUploadORM).where(
                SessionUploadORM.session_id == session_id,
                SessionUploadORM.sequence_number == sequence_number,
            )
            if device_id is None:
                q = q.where(SessionUploadORM.device_id.is_(None))
            else:
                q = q.where(SessionUploadORM.device_id == device_id)
            return s.scalars(q).first()

    def list_uploads(self, *, session_id: Optional[uuid.UUID] = None,
                     device_id: Optional[uuid.UUID] = None,
                     import_id: Optional[uuid.UUID] = None) -> "list[SessionUploadORM]":
        with self.Session() as s:
            q = select(SessionUploadORM)
            if session_id is not None:
                q = q.where(SessionUploadORM.session_id == session_id)
            if device_id is not None:
                q = q.where(SessionUploadORM.device_id == device_id)
            if import_id is not None:
                q = q.where(SessionUploadORM.import_id == import_id)
            return list(s.scalars(q).all())

    def move_upload_to_session(self, upload_id: uuid.UUID,
                               session_id: uuid.UUID) -> Optional[SessionUploadORM]:
        """Re-parent one upload onto another session (``services/session_split.py``).

        Its own method rather than a ``session_id`` entry in ``update_upload``'s
        allow-list: re-parenting drags the upload's streams and physio stats
        with it and invalidates both sessions' analyses, so it must not be
        reachable from a generic "patch these fields" call."""
        with self.Session() as s:
            orm = s.get(SessionUploadORM, upload_id)
            if orm is None:
                return None
            orm.session_id = session_id
            s.commit()
        return self.get_upload(upload_id)

    def update_upload(self, upload_id: uuid.UUID, changes: dict) -> Optional[SessionUploadORM]:
        allowed = ("status", "is_final", "raw_ref", "reanalysis_status",
                   "reanalysis_error", "physio_shared")
        with self.Session() as s:
            orm = s.get(SessionUploadORM, upload_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in allowed:
                    setattr(orm, k, v)
            s.commit()
        return self.get_upload(upload_id)

    def set_upload_status(self, upload_id: uuid.UUID, status: str) -> bool:
        return self.update_upload(upload_id, {"status": status}) is not None

    def set_reanalysis_status(self, upload_id: uuid.UUID, status: Optional[str],
                              error: Optional[str] = None) -> bool:
        """Track the background job started by reanalyze/wind-refresh
        (``routers/sessions.py``) — NULL status means idle/done."""
        return self.update_upload(
            upload_id, {"reanalysis_status": status, "reanalysis_error": error}
        ) is not None

    # --- session_streams ---

    def upsert_streams(self, session_upload_id: uuid.UUID,
                       streams: list[dict]) -> "list[SessionStreamORM]":
        """Upsert streams keyed by sensor_type within one upload.

        A device bundle's files (nav/imu/wind/pressure) arrive as independent
        storage events, so each worker callback carries only the sensors it
        just processed — replacing everything would clobber the others.
        Idempotent on callback retries."""
        sensor_types = {st.get("sensor_type") for st in streams}
        with self.Session() as s:
            for old in s.scalars(
                select(SessionStreamORM).where(
                    SessionStreamORM.session_upload_id == session_upload_id,
                    SessionStreamORM.sensor_type.in_(sensor_types),
                )
            ):
                s.delete(old)
            for st in streams:
                s.add(SessionStreamORM(
                    session_upload_id=session_upload_id,
                    **{k: st.get(k) for k in _STREAM_FIELDS if k in st},
                ))
            s.commit()
        return self.list_streams(session_upload_id)

    def list_streams(self, session_upload_id: uuid.UUID) -> "list[SessionStreamORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(SessionStreamORM).where(
                    SessionStreamORM.session_upload_id == session_upload_id
                )
            ).all())

    def list_streams_for_session(self, session_id: uuid.UUID) -> "list[SessionStreamORM]":
        """All streams of a session, joined through its uploads (race compute
        and the session streams endpoint read through this)."""
        with self.Session() as s:
            return list(s.scalars(
                select(SessionStreamORM)
                .join(SessionUploadORM,
                      SessionStreamORM.session_upload_id == SessionUploadORM.id)
                .where(SessionUploadORM.session_id == session_id)
            ).all())

    def list_streams_with_uploads_for_session(
        self, session_id: uuid.UUID
    ) -> "list[tuple[SessionStreamORM, SessionUploadORM]]":
        """Same join as ``list_streams_for_session`` but keeping the upload too.

        Needed wherever a stream can't be interpreted on its own: whose data is
        this (``subject_user_id``), may the caller see it (``physio_shared``),
        and which upload does the navigation track come from."""
        with self.Session() as s:
            return list(s.execute(
                select(SessionStreamORM, SessionUploadORM)
                .join(SessionUploadORM,
                      SessionStreamORM.session_upload_id == SessionUploadORM.id)
                .where(SessionUploadORM.session_id == session_id)
            ).all())

    # --- session_physio_stats ---

    def upsert_physio_stats(self, session_upload_id: uuid.UUID,
                            changes: dict) -> SessionPhysioStatsORM:
        """Merge (not replace) one crew member's physiological aggregates.

        The four physio files arrive as independent worker callbacks, each
        carrying only the metrics it could compute, so an absent key must leave
        the stored value alone — same reasoning as ``upsert_streams``."""
        with self.Session() as s:
            orm = s.get(SessionPhysioStatsORM, session_upload_id)
            if orm is None:
                orm = SessionPhysioStatsORM(session_upload_id=session_upload_id)
                s.add(orm)
            for k, v in changes.items():
                if k in _PHYSIO_STAT_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get_physio_stats(session_upload_id)

    def get_physio_stats(self, session_upload_id: uuid.UUID) -> Optional[SessionPhysioStatsORM]:
        with self.Session() as s:
            return s.get(SessionPhysioStatsORM, session_upload_id)

    def list_physio_stats_for_session(
        self, session_id: uuid.UUID
    ) -> "dict[uuid.UUID, SessionPhysioStatsORM]":
        """Physiological aggregates of every upload of a session, keyed by
        upload id — one entry per crew member who wore a device."""
        with self.Session() as s:
            rows = s.scalars(
                select(SessionPhysioStatsORM)
                .join(SessionUploadORM,
                      SessionPhysioStatsORM.session_upload_id == SessionUploadORM.id)
                .where(SessionUploadORM.session_id == session_id)
            ).all()
            return {r.session_upload_id: r for r in rows}
