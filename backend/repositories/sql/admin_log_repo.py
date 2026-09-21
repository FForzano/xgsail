"""SQL admin-access-log repository — append-only accountability rows.

Only two operations exist by design: append one row, and read the log back
newest first. There is deliberately no update or delete: a log an operator can
rewrite is not a log (pruning, if it is ever wanted, belongs in a migration or
a retention job, not behind an API).
"""

import uuid
from typing import Optional

from sqlalchemy import select

from ...db.models import AdminAccessLogORM


class SqlAdminLogRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def record(self, *, actor_user_id: Optional[uuid.UUID],
               target_user_id: Optional[uuid.UUID],
               action: str) -> AdminAccessLogORM:
        with self.Session() as s:
            row = AdminAccessLogORM(
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                action=action,
            )
            s.add(row)
            s.commit()
            s.refresh(row)
            s.expunge(row)
            return row

    def list(self, *, target_user_id: Optional[uuid.UUID] = None,
             limit: int = 50, offset: int = 0) -> "list[AdminAccessLogORM]":
        with self.Session() as s:
            q = select(AdminAccessLogORM)
            if target_user_id is not None:
                q = q.where(AdminAccessLogORM.target_user_id == target_user_id)
            q = (q.order_by(AdminAccessLogORM.created_at.desc(),
                            AdminAccessLogORM.id.desc())
                 .offset(offset).limit(limit))
            return list(s.scalars(q).all())
