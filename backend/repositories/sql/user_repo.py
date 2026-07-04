"""SQL user repository. Reads return ``UserORM`` (``to_dict()`` drops the
password hash); the hash is read only for login via a dedicated method."""

import uuid
from typing import Optional

from sqlalchemy import func, select

from ...db.models import UserORM


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

    def create(self, *, email: str, password_hash: Optional[str],
               first_name: Optional[str] = None, last_name: Optional[str] = None,
               terms_and_conditions: bool = False,
               is_active: bool = True, is_superadmin: bool = False) -> UserORM:
        with self.Session() as s:
            if self._by_email(s, email) is not None:
                raise ValueError(f"User already exists: {email}")
            orm = UserORM(
                email=email,
                password_hash=password_hash,
                first_name=first_name,
                last_name=last_name,
                terms_and_conditions=terms_and_conditions,
                is_active=is_active,
                is_superadmin=is_superadmin,
            )
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_by_id(new_id)

    def update(self, user_id: uuid.UUID, changes: dict) -> Optional[UserORM]:
        allowed = ("first_name", "last_name", "dob", "profile_image_id",
                   "terms_and_conditions", "password_hash")
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
        from datetime import datetime, timezone

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
