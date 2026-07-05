"""SQL boat repository: boats + ``user_boats`` membership + ``boat_classes``
catalog + ``boat_photos`` links. Reads return ORM rows; ``create``/``update``
take dicts (membership is managed via the dedicated member methods so a boat
edit never clobbers the roster)."""

import uuid
from typing import Optional

from sqlalchemy import select, update

from ...db.models import BoatClassORM, BoatORM, BoatPhotoORM, UserBoatORM

_FIELDS = ("name", "boat_class_id", "sail_number", "loa_m", "cert_id", "mbsa_id", "notes", "club_id")
_CLASS_FIELDS = ("name", "description", "logo_id")


class SqlBoatRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self) -> "list[BoatORM]":
        with self.Session() as s:
            return list(s.scalars(select(BoatORM)).all())

    def get(self, boat_id: uuid.UUID) -> Optional[BoatORM]:
        with self.Session() as s:
            return s.get(BoatORM, boat_id)

    def create(self, data: dict) -> BoatORM:
        with self.Session() as s:
            orm = BoatORM(**{k: data.get(k) for k in _FIELDS})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, boat_id: uuid.UUID, changes: dict) -> Optional[BoatORM]:
        with self.Session() as s:
            orm = s.get(BoatORM, boat_id)
            if orm is None:
                return None
            # Membership is never rewritten here (dedicated member methods do that).
            for k, v in changes.items():
                if k in _FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(boat_id)

    def delete(self, boat_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(BoatORM, boat_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    # --- ownership membership (user_boats) ---

    def add_member(self, boat_id: uuid.UUID, *, user_id: uuid.UUID,
                   role: str = "visitor",
                   default_sailing_role: Optional[str] = None) -> bool:
        with self.Session() as s:
            if s.get(BoatORM, boat_id) is None:
                return False
            exists = s.scalars(
                select(UserBoatORM).where(
                    UserBoatORM.boat_id == boat_id, UserBoatORM.user_id == user_id
                )
            ).first()
            if exists is not None:
                return False
            s.add(UserBoatORM(boat_id=boat_id, user_id=user_id, role=role,
                              default_sailing_role=default_sailing_role))
            s.commit()
            return True

    def remove_member(self, boat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.scalars(
                select(UserBoatORM).where(
                    UserBoatORM.boat_id == boat_id, UserBoatORM.user_id == user_id
                )
            ).first()
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def set_member_role(self, boat_id: uuid.UUID, user_id: uuid.UUID, role: str) -> bool:
        with self.Session() as s:
            res = s.execute(
                update(UserBoatORM)
                .where(UserBoatORM.boat_id == boat_id, UserBoatORM.user_id == user_id)
                .values(role=role)
            )
            s.commit()
            return res.rowcount > 0

    def list_members(self, boat_id: uuid.UUID) -> "list[UserBoatORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(UserBoatORM).where(UserBoatORM.boat_id == boat_id)
            ).all())

    def is_member(self, boat_id: uuid.UUID, user_id: uuid.UUID,
                  roles: "Optional[list]" = None) -> bool:
        with self.Session() as s:
            q = select(UserBoatORM).where(
                UserBoatORM.boat_id == boat_id, UserBoatORM.user_id == user_id
            )
            if roles is not None:
                q = q.where(UserBoatORM.role.in_(roles))
            return s.scalars(q).first() is not None

    def list_boats_for_user(self, user_id: uuid.UUID,
                            roles: "Optional[list]" = None) -> "list[BoatORM]":
        with self.Session() as s:
            q = (
                select(BoatORM)
                .join(UserBoatORM, UserBoatORM.boat_id == BoatORM.id)
                .where(UserBoatORM.user_id == user_id)
            )
            if roles is not None:
                q = q.where(UserBoatORM.role.in_(roles))
            return list(s.scalars(q).all())

    # --- boat_classes catalog ---

    def list_classes(self) -> "list[BoatClassORM]":
        with self.Session() as s:
            return list(s.scalars(select(BoatClassORM)).all())

    def get_class(self, class_id: uuid.UUID) -> Optional[BoatClassORM]:
        with self.Session() as s:
            return s.get(BoatClassORM, class_id)

    def create_class(self, data: dict) -> BoatClassORM:
        with self.Session() as s:
            orm = BoatClassORM(**{k: data.get(k) for k in _CLASS_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_class(new_id)

    def update_class(self, class_id: uuid.UUID, changes: dict) -> Optional[BoatClassORM]:
        with self.Session() as s:
            orm = s.get(BoatClassORM, class_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _CLASS_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get_class(class_id)

    def delete_class(self, class_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(BoatClassORM, class_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    # --- boat_photos links ---

    def list_photos(self, boat_id: uuid.UUID) -> "list[BoatPhotoORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(BoatPhotoORM).where(BoatPhotoORM.boat_id == boat_id)
            ).all())

    def add_photo(self, boat_id: uuid.UUID, image_id: uuid.UUID) -> BoatPhotoORM:
        with self.Session() as s:
            orm = BoatPhotoORM(boat_id=boat_id, image_id=image_id)
            s.add(orm)
            s.commit()
            s.refresh(orm)
            s.expunge(orm)
            return orm

    def get_photo(self, boat_id: uuid.UUID, image_id: uuid.UUID) -> Optional[BoatPhotoORM]:
        with self.Session() as s:
            return s.scalars(
                select(BoatPhotoORM).where(
                    BoatPhotoORM.boat_id == boat_id, BoatPhotoORM.image_id == image_id
                )
            ).first()

    def remove_photo(self, boat_id: uuid.UUID, image_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.scalars(
                select(BoatPhotoORM).where(
                    BoatPhotoORM.boat_id == boat_id, BoatPhotoORM.image_id == image_id
                )
            ).first()
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True
