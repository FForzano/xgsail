"""SQL session repository.

Phase 5: the **DB is the source of truth** for session metadata (owner,
crew, visibility, boat_id snapshot). The ingest pipeline writes rows via
``upsert``; reads serve straight from the table and must NOT reconcile from the
blob manifests on every call — that would clobber the user-driven privacy
fields. The blob→DB import is now a **one-shot** ``bootstrap_from_blob`` (run at
migration/bootstrap), plus a read-only fallback in ``get`` for a historical
session not yet imported (it does not write back).
"""

from typing import Optional

from sqlalchemy import select

from ... import domain
from ...db.models import SessionORM, SessionCrewORM
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
        # Phase 5 privacy/attribution fields.
        orm.owner_user_id = session.owner_user_id
        orm.boat_id = session.boat_id
        orm.visibility = session.visibility or "private"
        orm.club_id = session.club_id
        orm.group_id = session.group_id
        orm.regatta_id = session.regatta_id
        orm.race_id = session.race_id
        # Crew is replaced wholesale from the domain object (the PATCH endpoint
        # reads-modifies-writes the full list; ingest creates with none).
        s.flush()  # ensure orm.id for the crew rows
        for c in list(orm.crew):
            s.delete(c)
        orm.crew = [
            SessionCrewORM(
                session_id=orm.id,
                user_id=c.user_id,
                guest_name=c.guest_name,
                boat_role=c.boat_role,
            )
            for c in session.crew
        ]

    def upsert(self, session: domain.Session) -> domain.Session:
        with self.Session() as s:
            self._write(s, session)
            s.commit()
        return session

    def bootstrap_from_blob(self) -> int:
        """One-shot import of blob manifests into the table (migration/bootstrap
        helper). Only inserts rows that do not exist yet, so it never overwrites
        DB-authoritative privacy fields. Returns the number imported."""
        imported = 0
        with self.Session() as s:
            for sess in self._blob_repo.list():
                exists = s.scalars(
                    select(SessionORM).where(
                        SessionORM.device_id == sess.device_id,
                        SessionORM.date == sess.date,
                    )
                ).first()
                if exists is None:
                    self._write(s, sess)
                    imported += 1
            s.commit()
        return imported

    def list(self) -> list[domain.Session]:
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
        # Read-only fallback for a historical session not yet imported. Does NOT
        # write back — bootstrap_from_blob() is the one place that populates.
        return self._blob_repo.get(device_id, date)
