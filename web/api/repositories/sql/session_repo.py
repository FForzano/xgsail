"""SQL session repository.

The processing pipeline writes session manifests to the blob store, so this
repo keeps the ``sessions`` table populated from those manifests: ``upsert`` is
called by the ingest pipeline, and reads lazily backfill from blob if the table
is empty / a row is missing. The table then serves SQL queries without ever
diverging from the manifests (the source of truth).
"""

from typing import Optional

from sqlalchemy import select

from ... import domain
from ...db.models import SessionORM
from ..base import SessionRepo
from ..object.session_repo import ObjectSessionRepo
from . import _mappers as M


class SqlSessionRepo(SessionRepo):
    def __init__(self, session_factory, blob, data_prefix: str):
        self.Session = session_factory
        self._blob_repo = ObjectSessionRepo(blob, data_prefix)

    def _write(self, s, session: domain.Session) -> None:
        orm = s.scalars(
            select(SessionORM).where(
                SessionORM.device_id == session.device_id,
                SessionORM.date == session.date,
            )
        ).first()
        if orm is None:
            orm = SessionORM(device_id=session.device_id, date=session.date)
            s.add(orm)
        orm.session_id = session.session_id
        orm.start_time = session.start_time
        orm.end_time = session.end_time
        orm.duration_sec = session.duration_sec
        orm.boat = session.boat
        orm.name = session.name
        orm.sensors = session.sensors
        orm.has_video = session.has_video
        orm.has_analysis = session.has_analysis
        orm.trim = session.trim

    def upsert(self, session: domain.Session) -> domain.Session:
        with self.Session() as s:
            self._write(s, session)
            s.commit()
        return session

    def list(self) -> list[domain.Session]:
        # Manifests in the blob store are the source of truth (written by the
        # processing pipeline). Reconcile the table with them, then serve from
        # the table. Cheap at fleet scale (handful of sessions).
        manifests = self._blob_repo.list()
        if manifests:
            with self.Session() as s:
                for sess in manifests:
                    self._write(s, sess)
                s.commit()
        with self.Session() as s:
            return [M.session_to_domain(r) for r in s.scalars(select(SessionORM)).all()]

    def get(self, device_id: str, date: str) -> Optional[domain.Session]:
        with self.Session() as s:
            orm = s.scalars(
                select(SessionORM).where(
                    SessionORM.device_id == device_id,
                    SessionORM.date == date,
                )
            ).first()
            if orm is not None:
                return M.session_to_domain(orm)
        # Miss: fall back to the blob manifest and populate the table.
        sess = self._blob_repo.get(device_id, date)
        if sess is not None:
            self.upsert(sess)
        return sess
