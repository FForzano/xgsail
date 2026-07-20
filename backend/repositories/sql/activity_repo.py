"""SQL activity repository: ``activities`` + their per-activity ``marks``.

An activity groups N sessions (boats) over a time window (solo outing, group
training, or a tracked race via ``race_id``). Marks hang off the activity so
trainings get buoys too (see docs/er-project.md).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, or_, select

from ...db.models import (
    ActivityORM,
    MarkORM,
    PermissionORM,
    RolePermissionORM,
    SessionCrewORM,
    SessionORM,
    UserClubORM,
    UserGroupORM,
    UserRoleORM,
)

_FIELDS = ("name", "type", "club_id", "race_id", "created_by", "group_id",
           "visibility", "status", "description", "started_at", "ended_at",
           "thumbnail_image_id")
_MARK_FIELDS = ("mark_role", "lat", "lng", "set_at")


class SqlActivityRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def _visibility_clause(self, viewer_id: Optional[uuid.UUID]):
        """SQL equivalent of ``auth.permissions.activity_visible_to``, so
        visibility can be applied *before* LIMIT/OFFSET — filtering it in
        Python after the DB page comes back (the old approach) would make
        pages come back short/empty whenever some rows in that page are
        invisible to the viewer."""
        conditions = [ActivityORM.visibility == "public"]
        if viewer_id is None:
            return or_(*conditions)
        conditions.append(ActivityORM.created_by == viewer_id)
        crew_activity_ids = (
            select(SessionORM.activity_id)
            .join(SessionCrewORM, SessionCrewORM.session_id == SessionORM.id)
            .where(SessionCrewORM.user_id == viewer_id)
        )
        conditions.append(ActivityORM.id.in_(crew_activity_ids))
        member_club_ids = select(UserClubORM.club_id).where(
            UserClubORM.user_id == viewer_id,
            UserClubORM.status == "active",
        )
        club_manage_ids = (
            select(UserRoleORM.scope_club_id)
            .join(RolePermissionORM, RolePermissionORM.role_id == UserRoleORM.role_id)
            .join(PermissionORM, PermissionORM.id == RolePermissionORM.permission_id)
            .where(
                UserRoleORM.user_id == viewer_id,
                PermissionORM.key == "club.manage",
                UserRoleORM.scope_club_id.isnot(None),
            )
        )
        # A global (unscoped) club.manage grant applies to every club, so it
        # can't be folded into the club_manage_ids IN-list above (NULL never
        # matches an IN against non-null ids) — checked as its own EXISTS.
        has_global_club_manage = (
            select(UserRoleORM.id)
            .join(RolePermissionORM, RolePermissionORM.role_id == UserRoleORM.role_id)
            .join(PermissionORM, PermissionORM.id == RolePermissionORM.permission_id)
            .where(
                UserRoleORM.user_id == viewer_id,
                UserRoleORM.scope_club_id.is_(None),
                PermissionORM.key == "club.manage",
            )
            .exists()
        )
        conditions.append(and_(
            ActivityORM.visibility == "club",
            or_(
                ActivityORM.club_id.in_(member_club_ids),
                ActivityORM.club_id.in_(club_manage_ids),
                has_global_club_manage,
            ),
        ))
        member_group_ids = select(UserGroupORM.group_id).where(
            UserGroupORM.user_id == viewer_id,
            UserGroupORM.status == "active",
            UserGroupORM.deleted_at.is_(None),
        )
        conditions.append(and_(
            ActivityORM.visibility == "group",
            ActivityORM.group_id.in_(member_group_ids),
        ))
        return or_(*conditions)

    def list(self, *, club_id: Optional[uuid.UUID] = None,
             group_id: Optional[uuid.UUID] = None,
             race_id: Optional[uuid.UUID] = None,
             type: Optional[str] = None,
             status: Optional[str] = None,
             created_by: Optional[uuid.UUID] = None,
             member_of_user: Optional[uuid.UUID] = None,
             viewer_id: Optional[uuid.UUID] = None,
             viewer_is_superadmin: bool = False,
             limit: Optional[int] = None,
             offset: int = 0) -> "list[ActivityORM]":
        with self.Session() as s:
            q = select(ActivityORM).order_by(ActivityORM.started_at.desc())
            if club_id is not None:
                q = q.where(ActivityORM.club_id == club_id)
            if group_id is not None:
                q = q.where(ActivityORM.group_id == group_id)
            if race_id is not None:
                q = q.where(ActivityORM.race_id == race_id)
            if type is not None:
                q = q.where(ActivityORM.type == type)
            if status is not None:
                q = q.where(ActivityORM.status == status)
            if created_by is not None:
                q = q.where(ActivityORM.created_by == created_by)
            if member_of_user is not None:
                member_club_ids = select(UserClubORM.club_id).where(
                    UserClubORM.user_id == member_of_user,
                    UserClubORM.status == "active",
                )
                member_group_ids = select(UserGroupORM.group_id).where(
                    UserGroupORM.user_id == member_of_user,
                    UserGroupORM.status == "active",
                    UserGroupORM.deleted_at.is_(None),
                )
                q = q.where(or_(
                    ActivityORM.club_id.in_(member_club_ids),
                    ActivityORM.group_id.in_(member_group_ids),
                ))
            if not viewer_is_superadmin:
                q = q.where(self._visibility_clause(viewer_id))
            q = q.offset(offset)
            if limit is not None:
                q = q.limit(limit)
            return list(s.scalars(q).all())

    def list_upcoming_for_user(self, user_id: uuid.UUID, *, limit: int = 5) -> "list[ActivityORM]":
        """Announced (``planned``) events with a future date, belonging to a
        club/group the user actively belongs to — the "in arrivo" feed."""
        with self.Session() as s:
            club_ids = select(UserClubORM.club_id).where(
                UserClubORM.user_id == user_id,
                UserClubORM.status == "active",
                UserClubORM.deleted_at.is_(None),
            )
            group_ids = select(UserGroupORM.group_id).where(
                UserGroupORM.user_id == user_id,
                UserGroupORM.status == "active",
                UserGroupORM.deleted_at.is_(None),
            )
            q = (
                select(ActivityORM)
                .where(ActivityORM.status == "planned")
                .where(ActivityORM.started_at.isnot(None))
                .where(ActivityORM.started_at >= datetime.now(timezone.utc))
                .where(or_(
                    ActivityORM.club_id.in_(club_ids),
                    ActivityORM.group_id.in_(group_ids),
                ))
                .order_by(ActivityORM.started_at.asc())
                .limit(limit)
            )
            return list(s.scalars(q).all())

    def get(self, activity_id: uuid.UUID) -> Optional[ActivityORM]:
        with self.Session() as s:
            return s.get(ActivityORM, activity_id)

    def get_by_race(self, race_id: uuid.UUID) -> Optional[ActivityORM]:
        """THE activity tracking a race (first match)."""
        with self.Session() as s:
            return s.scalars(
                select(ActivityORM).where(ActivityORM.race_id == race_id)
            ).first()

    def create(self, data: dict) -> ActivityORM:
        with self.Session() as s:
            orm = ActivityORM(**{k: data.get(k) for k in _FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, activity_id: uuid.UUID, changes: dict) -> Optional[ActivityORM]:
        with self.Session() as s:
            orm = s.get(ActivityORM, activity_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(activity_id)

    def delete(self, activity_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(ActivityORM, activity_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def extend_window(self, activity_id: uuid.UUID, started_at: Optional[datetime],
                      ended_at: Optional[datetime]) -> None:
        """Widen the activity's own bounds monotonically (min start, max end)
        — keeps it in sync with every session ever attached to it, since
        sessions extend their own window independently (see
        ``services.ingestion.find_or_create_session``)."""
        with self.Session() as s:
            orm = s.get(ActivityORM, activity_id)
            if orm is None:
                return
            if started_at is not None and (orm.started_at is None or started_at < orm.started_at):
                orm.started_at = started_at
            if ended_at is not None and (orm.ended_at is None or ended_at > orm.ended_at):
                orm.ended_at = ended_at
            s.commit()

    # --- marks ---

    def list_marks(self, activity_id: uuid.UUID) -> "list[MarkORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(MarkORM).where(MarkORM.activity_id == activity_id)
            ).all())

    def get_mark(self, mark_id: uuid.UUID) -> Optional[MarkORM]:
        with self.Session() as s:
            return s.get(MarkORM, mark_id)

    def add_mark(self, activity_id: uuid.UUID, data: dict) -> MarkORM:
        with self.Session() as s:
            orm = MarkORM(activity_id=activity_id,
                          **{k: data.get(k) for k in _MARK_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_mark(new_id)

    def update_mark(self, mark_id: uuid.UUID, changes: dict) -> Optional[MarkORM]:
        with self.Session() as s:
            orm = s.get(MarkORM, mark_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _MARK_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get_mark(mark_id)

    def delete_mark(self, mark_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(MarkORM, mark_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def replace_marks(self, activity_id: uuid.UUID, marks: "list[dict]") -> "list[MarkORM]":
        """Atomic replace — used by suggest-marks ``apply``."""
        with self.Session() as s:
            for old in s.scalars(select(MarkORM).where(MarkORM.activity_id == activity_id)):
                s.delete(old)
            for m in marks:
                s.add(MarkORM(activity_id=activity_id,
                              **{k: m.get(k) for k in _MARK_FIELDS if k in m}))
            s.commit()
        return self.list_marks(activity_id)
