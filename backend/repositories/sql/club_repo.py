"""SQL club repository (+ membership via ``user_clubs``). Reads return
``ClubORM`` (members embedded via ``to_dict``); membership ops take explicit
ids. Ownership is no longer a column — it's the scoped ``club_admin`` role."""

import uuid
from typing import Optional

from sqlalchemy import select, update

from ...db.models import ClubORM, UserClubORM


class SqlClubRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self) -> "list[ClubORM]":
        with self.Session() as s:
            return list(s.scalars(select(ClubORM)).all())

    def get(self, club_id: uuid.UUID) -> Optional[ClubORM]:
        with self.Session() as s:
            return s.get(ClubORM, club_id)

    def create(self, data: dict) -> ClubORM:
        with self.Session() as s:
            orm = ClubORM(**{k: v for k, v in data.items() if k != "members"})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def add_member(self, club_id: uuid.UUID, *, user_id: uuid.UUID,
                   status: str = "invited") -> bool:
        with self.Session() as s:
            exists = s.scalars(
                select(UserClubORM).where(
                    UserClubORM.club_id == club_id,
                    UserClubORM.user_id == user_id,
                )
            ).first()
            if exists is not None:
                return False
            s.add(UserClubORM(club_id=club_id, user_id=user_id, status=status))
            s.commit()
            return True

    def set_member_status(self, club_id: uuid.UUID, user_id: uuid.UUID, status: str) -> bool:
        with self.Session() as s:
            res = s.execute(
                update(UserClubORM)
                .where(UserClubORM.club_id == club_id, UserClubORM.user_id == user_id)
                .values(status=status)
            )
            s.commit()
            return res.rowcount > 0

    def update(self, club_id: uuid.UUID, changes: dict) -> Optional[ClubORM]:
        allowed = ("name", "description", "address_line_1", "address_line_2",
                   "city", "state_province", "postal_code", "country", "lat", "lng",
                   "founded_year", "website", "contact_email", "logo_id", "is_active")
        with self.Session() as s:
            orm = s.get(ClubORM, club_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in allowed:
                    setattr(orm, k, v)
            s.commit()
        return self.get(club_id)

    def list_members(self, club_id: uuid.UUID) -> "list[UserClubORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(UserClubORM).where(UserClubORM.club_id == club_id)
            ).all())

    def get_member(self, club_id: uuid.UUID, user_id: uuid.UUID) -> Optional[UserClubORM]:
        with self.Session() as s:
            return s.scalars(
                select(UserClubORM).where(
                    UserClubORM.club_id == club_id, UserClubORM.user_id == user_id
                )
            ).first()

    def remove_member(self, club_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Soft removal: status=deleted + deleted_at (history preserved)."""
        from datetime import datetime, timezone

        with self.Session() as s:
            orm = s.scalars(
                select(UserClubORM).where(
                    UserClubORM.club_id == club_id, UserClubORM.user_id == user_id
                )
            ).first()
            if orm is None:
                return False
            orm.status = "deleted"
            orm.deleted_at = datetime.now(timezone.utc)
            s.commit()
            return True

    def list_memberships_for_user(self, user_id: uuid.UUID) -> "list[dict]":
        """My club memberships (incl. pending invites), with the club name —
        powers ``GET /api/users/me/memberships``."""
        with self.Session() as s:
            rows = s.execute(
                select(UserClubORM, ClubORM.name)
                .join(ClubORM, ClubORM.id == UserClubORM.club_id)
                .where(
                    UserClubORM.user_id == user_id,
                    UserClubORM.status != "deleted",
                    ClubORM.is_active.is_(True),
                )
            ).all()
            return [
                {"club_id": m.club_id, "name": name, "status": m.status,
                 "created_at": m.created_at}
                for m, name in rows
            ]

    def is_active_member(self, club_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        with self.Session() as s:
            return s.scalars(
                select(UserClubORM).where(
                    UserClubORM.club_id == club_id,
                    UserClubORM.user_id == user_id,
                    UserClubORM.status == "active",
                )
            ).first() is not None
