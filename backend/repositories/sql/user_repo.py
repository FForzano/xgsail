"""SQL user repository. Reads return ``UserORM`` (``to_dict()`` drops the
password hash); the hash is read only for login via a dedicated method."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_, select

from ...db.models import UserORM
from ...db.models.boat import UserBoatORM
from ...db.models.club import UserClubORM
from ...db.models.group import UserGroupORM
from ...support import DONATED_DELAY, SNOOZE_DELAY


class SqlUserRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self) -> list[UserORM]:
        with self.Session() as s:
            return list(s.scalars(select(UserORM)).all())

    def get_by_id(self, user_id: uuid.UUID) -> Optional[UserORM]:
        with self.Session() as s:
            return s.get(UserORM, user_id)

    def get_by_email(self, email: str) -> Optional[UserORM]:
        with self.Session() as s:
            return self._by_email(s, email)

    def get_password_hash_by_email(self, email: str) -> Optional[str]:
        with self.Session() as s:
            orm = self._by_email(s, email)
            return orm.password_hash if orm else None

    def search(self, q: str, *, limit: int = 20) -> "list[UserORM]":
        """Case-insensitive partial (``%q%``, not prefix-only) match on first
        name, last name, email, and the "first last" full-name concatenation
        — so "mario rossi" finds first_name="Mario"/last_name="Rossi" even
        though neither column alone contains the full string. Uses ``+``
        rather than ``func.concat`` because the test suite runs against
        SQLite, which lacks ``concat``. Only live users (active, not soft-
        deleted) are eligible. Caller is responsible for any minimum-length
        guard on ``q``."""
        pattern = f"%{q}%"
        full_name = func.coalesce(UserORM.first_name, "") + " " + func.coalesce(UserORM.last_name, "")
        with self.Session() as s:
            stmt = (
                select(UserORM)
                .where(
                    UserORM.is_active.is_(True),
                    UserORM.deleted_at.is_(None),
                    or_(
                        UserORM.first_name.ilike(pattern),
                        UserORM.last_name.ilike(pattern),
                        UserORM.email.ilike(pattern),
                        full_name.ilike(pattern),
                    ),
                )
                .order_by(UserORM.last_name, UserORM.first_name)
                .limit(limit)
            )
            return list(s.scalars(stmt).all())

    def related_user_ids(self, user_id: uuid.UUID) -> "set[uuid.UUID]":
        """Every other user sharing at least one club, group, or boat with
        ``user_id`` — one simple query per membership table rather than a
        single clever join, for readability."""
        with self.Session() as s:
            club_ids = s.scalars(
                select(UserClubORM.club_id).where(UserClubORM.user_id == user_id)
            ).all()
            group_ids = s.scalars(
                select(UserGroupORM.group_id).where(UserGroupORM.user_id == user_id)
            ).all()
            boat_ids = s.scalars(
                select(UserBoatORM.boat_id).where(UserBoatORM.user_id == user_id)
            ).all()

            related: set[uuid.UUID] = set()
            if club_ids:
                related.update(s.scalars(
                    select(UserClubORM.user_id).where(UserClubORM.club_id.in_(club_ids))
                ).all())
            if group_ids:
                related.update(s.scalars(
                    select(UserGroupORM.user_id).where(UserGroupORM.group_id.in_(group_ids))
                ).all())
            if boat_ids:
                related.update(s.scalars(
                    select(UserBoatORM.user_id).where(UserBoatORM.boat_id.in_(boat_ids))
                ).all())

            related.discard(user_id)
            return related

    def create(self, *, email: str, password_hash: Optional[str],
               first_name: Optional[str] = None, last_name: Optional[str] = None,
               terms_and_conditions: bool = False,
               terms_version: Optional[str] = None,
               privacy_version: Optional[str] = None,
               is_active: bool = True, is_superadmin: bool = False) -> UserORM:
        now = datetime.now(timezone.utc)
        with self.Session() as s:
            if self._by_email(s, email) is not None:
                raise ValueError(f"User already exists: {email}")
            orm = UserORM(
                email=email,
                password_hash=password_hash,
                first_name=first_name,
                last_name=last_name,
                terms_and_conditions=terms_and_conditions,
                terms_version=terms_version,
                terms_accepted_at=now if terms_version else None,
                privacy_version=privacy_version,
                privacy_accepted_at=now if privacy_version else None,
                is_active=is_active,
                is_superadmin=is_superadmin,
            )
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_by_id(new_id)

    def record_legal_acceptance(self, user_id: uuid.UUID, *,
                                terms_version: Optional[str] = None,
                                privacy_version: Optional[str] = None) -> Optional[UserORM]:
        """Stamp acceptance of the current legal document version(s) with the
        current timestamp. Only the documents passed are updated."""
        now = datetime.now(timezone.utc)
        with self.Session() as s:
            orm = s.get(UserORM, user_id)
            if orm is None:
                return None
            if terms_version is not None:
                orm.terms_version = terms_version
                orm.terms_accepted_at = now
                orm.terms_and_conditions = True
            if privacy_version is not None:
                orm.privacy_version = privacy_version
                orm.privacy_accepted_at = now
            s.commit()
        return self.get_by_id(user_id)

    def record_support_prompt(self, user_id: uuid.UUID, *, donated: bool) -> Optional[UserORM]:
        """Record that the support-reminder banner was shown and dismissed
        (optionally with a donation confirmation), scheduling the next
        eligible prompt accordingly."""
        now = datetime.now(timezone.utc)
        with self.Session() as s:
            orm = s.get(UserORM, user_id)
            if orm is None:
                return None
            if donated:
                orm.support_donated_at = now
                orm.support_prompt_next_at = now + DONATED_DELAY
            else:
                orm.support_prompt_next_at = now + SNOOZE_DELAY
            s.commit()
        return self.get_by_id(user_id)

    def mark_onboarding_tour_seen(self, user_id: uuid.UUID, tour_id: str) -> Optional[UserORM]:
        """Record that the logged-in user finished or skipped a guided-tour
        (see capabilities ``onboarding.seenTours``) — idempotent, and tracked
        as an open-ended set so new tours never need a migration."""
        with self.Session() as s:
            orm = s.get(UserORM, user_id)
            if orm is None:
                return None
            seen = set(json.loads(orm.onboarding_seen_tours or "[]"))
            seen.add(tour_id)
            orm.onboarding_seen_tours = json.dumps(sorted(seen))
            s.commit()
        return self.get_by_id(user_id)

    def update(self, user_id: uuid.UUID, changes: dict) -> Optional[UserORM]:
        allowed = ("first_name", "last_name", "dob", "profile_image_id",
                   "terms_and_conditions", "password_hash", "unit_system",
                   "resting_hr_bpm", "max_hr_bpm")
        with self.Session() as s:
            orm = s.get(UserORM, user_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in allowed:
                    setattr(orm, k, v)
            s.commit()
        return self.get_by_id(user_id)

    def soft_delete(self, user_id: uuid.UUID) -> bool:
        """Matrix delete = soft: status=deleted, deactivated, timestamped."""
        with self.Session() as s:
            orm = s.get(UserORM, user_id)
            if orm is None:
                return False
            orm.status = "deleted"
            orm.is_active = False
            orm.deleted_at = datetime.now(timezone.utc)
            s.commit()
            return True

    @staticmethod
    def _by_email(s, email: str) -> Optional[UserORM]:
        return s.scalars(
            select(UserORM).where(func.lower(UserORM.email) == email.lower())
        ).first()
