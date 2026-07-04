"""SQL polar repository: ``polar_points`` at three granularities.

Exactly one of class_id/boat_id/session_id is set per row (DB CHECK). Curves
are replaced wholesale per target (``bulk_upsert`` = delete+insert) — a polar
is meaningful as a set, not point by point.
"""

import uuid
from typing import Optional

from sqlalchemy import select

from ...db.models import PolarPointORM

_POINT_FIELDS = ("source", "twa_deg", "tws_kts", "speed_kts", "vmg_kts", "sample_count")


def _target_clauses(class_id, boat_id, session_id):
    clauses = []
    clauses.append(PolarPointORM.class_id == class_id if class_id is not None
                   else PolarPointORM.class_id.is_(None))
    clauses.append(PolarPointORM.boat_id == boat_id if boat_id is not None
                   else PolarPointORM.boat_id.is_(None))
    clauses.append(PolarPointORM.session_id == session_id if session_id is not None
                   else PolarPointORM.session_id.is_(None))
    return clauses


class SqlPolarRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self, *, class_id: Optional[uuid.UUID] = None,
             boat_id: Optional[uuid.UUID] = None,
             session_id: Optional[uuid.UUID] = None) -> "list[PolarPointORM]":
        """Points for ONE target (pass exactly one id)."""
        with self.Session() as s:
            return list(s.scalars(
                select(PolarPointORM).where(*_target_clauses(class_id, boat_id, session_id))
            ).all())

    def get(self, point_id: uuid.UUID) -> Optional[PolarPointORM]:
        with self.Session() as s:
            return s.get(PolarPointORM, point_id)

    def bulk_upsert(self, *, class_id: Optional[uuid.UUID] = None,
                    boat_id: Optional[uuid.UUID] = None,
                    session_id: Optional[uuid.UUID] = None,
                    source: str, points: "list[dict]") -> int:
        """Replace the whole curve for one target. Returns points written."""
        target = {"class_id": class_id, "boat_id": boat_id, "session_id": session_id}
        with self.Session() as s:
            for old in s.scalars(
                select(PolarPointORM).where(*_target_clauses(class_id, boat_id, session_id))
            ):
                s.delete(old)
            for p in points:
                s.add(PolarPointORM(
                    **target, source=source,
                    **{k: p.get(k) for k in _POINT_FIELDS if k in p and k != "source"},
                ))
            s.commit()
            return len(points)

    def delete_for_target(self, *, class_id: Optional[uuid.UUID] = None,
                          boat_id: Optional[uuid.UUID] = None,
                          session_id: Optional[uuid.UUID] = None) -> int:
        with self.Session() as s:
            rows = list(s.scalars(
                select(PolarPointORM).where(*_target_clauses(class_id, boat_id, session_id))
            ))
            for r in rows:
                s.delete(r)
            s.commit()
            return len(rows)
