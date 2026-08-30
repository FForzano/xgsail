"""SQL boat repository: boats + ``user_boats`` membership + ``boat_classes``
catalog + ``boat_photos`` links + ``boat_notes`` (rig-tuning notebook). Reads
return ORM rows; ``create``/``update`` take dicts (membership is managed via
the dedicated member methods so a boat edit never clobbers the roster)."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, or_, select, update

from ...db.models import (
    BoatClaimORM, BoatClassORM, BoatNoteORM, BoatORM, BoatPhotoORM, DeviceORM,
    LiveRecordingORM, OfficialStandingsORM, PolarPointORM, RegattaEntryORM,
    ResultORM, SessionORM, UserBoatORM,
)
from ...db.models.boat import USER_BOAT_ROLES

_FIELDS = (
    "name", "boat_class_id", "sail_number", "loa_m", "cert_id", "mbsa_id", "club_id",
    "is_guest", "guest_created_by",
)
# The guest flags are set once, at creation: dropping the placeholder status is
# what the claim flow does (``clear_guest``), never a plain boat edit.
_UPDATABLE_FIELDS = tuple(f for f in _FIELDS if f not in ("is_guest", "guest_created_by"))
# owner > admin > visitor, for picking the surviving role in a boat merge.
_ROLE_RANK = {role: rank for rank, role in enumerate(reversed(USER_BOAT_ROLES))}
_NOTE_FIELDS = ("title", "body")
_CLASS_FIELDS = (
    "name", "description", "logo_id",
    "loa_m", "beam_m", "sail_area_sqm", "crew_size", "hull_type",
    "rig_type", "spinnaker_type", "py_rating", "rya_class_id",
)


class SqlBoatRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def _text_filter(self, stmt, q: Optional[str]):
        if not q:
            return stmt
        like = f"%{q.strip()}%"
        matching_classes = select(BoatClassORM.id).where(BoatClassORM.name.ilike(like))
        return stmt.where(or_(
            BoatORM.name.ilike(like),
            BoatORM.sail_number.ilike(like),
            BoatORM.boat_class_id.in_(matching_classes),
        ))

    def list(self, *, q: Optional[str] = None,
             limit: Optional[int] = None, offset: int = 0,
             include_guest: bool = False) -> "list[BoatORM]":
        """Boats, optionally filtered by a free-text query on name, sail
        number, or class name.

        Guest boats are excluded unless ``include_guest``: this feeds the
        instance-wide BoatPicker that enters boats in regattas, and an
        unverified placeholder somebody created for one outing must not
        pollute that authoritative namespace. ``list_boats_for_user`` (the
        ``mine=true`` path) deliberately keeps returning them — they are the
        creator's own boats.

        Always paginate from the API: this table grows with every user on the
        instance, and the callers that used to pull it whole (the results
        editor's boat select) became unusable well before that."""
        with self.Session() as s:
            stmt = self._text_filter(select(BoatORM), q)
            if not include_guest:
                stmt = stmt.where(BoatORM.is_guest.is_(False))
            stmt = stmt.order_by(BoatORM.name.asc()).offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)
            return list(s.scalars(stmt).all())

    def list_claimable(self, *, q: str, limit: int, offset: int = 0) -> "list[BoatORM]":
        """Guest boats matching ``q`` — the search behind "is this my boat?".
        Search-only by design (``q`` is required): the point is to find one
        known boat, not to browse every placeholder on the instance."""
        with self.Session() as s:
            stmt = self._text_filter(
                select(BoatORM).where(BoatORM.is_guest.is_(True)), q
            )
            stmt = stmt.order_by(BoatORM.name.asc()).offset(offset).limit(limit)
            return list(s.scalars(stmt).all())

    def get(self, boat_id: uuid.UUID) -> Optional[BoatORM]:
        with self.Session() as s:
            return s.get(BoatORM, boat_id)

    def create(self, data: dict) -> BoatORM:
        with self.Session() as s:
            # ``if k in data`` (as in create_class): passing is_guest=None
            # explicitly would override the column default and insert NULL
            # into a NOT NULL column.
            orm = BoatORM(**{k: data.get(k) for k in _FIELDS if k in data})
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
                if k in _UPDATABLE_FIELDS:
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

    def set_member_role(self, boat_id: uuid.UUID, user_id: uuid.UUID, *,
                        role: Optional[str] = None,
                        default_sailing_role: Optional[str] = None) -> bool:
        values = {}
        if role is not None:
            values["role"] = role
        if default_sailing_role is not None:
            values["default_sailing_role"] = default_sailing_role
        if not values:
            return False
        with self.Session() as s:
            res = s.execute(
                update(UserBoatORM)
                .where(UserBoatORM.boat_id == boat_id, UserBoatORM.user_id == user_id)
                .values(**values)
            )
            s.commit()
            return res.rowcount > 0

    def list_members(self, boat_id: uuid.UUID) -> "list[UserBoatORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(UserBoatORM).where(UserBoatORM.boat_id == boat_id)
            ).all())

    def get_member(self, boat_id: uuid.UUID, user_id: uuid.UUID) -> Optional[UserBoatORM]:
        with self.Session() as s:
            return s.scalars(
                select(UserBoatORM).where(
                    UserBoatORM.boat_id == boat_id, UserBoatORM.user_id == user_id
                )
            ).first()

    def count_owners(self, boat_id: uuid.UUID) -> int:
        with self.Session() as s:
            return s.scalar(
                select(func.count()).select_from(UserBoatORM).where(
                    UserBoatORM.boat_id == boat_id, UserBoatORM.role == "owner"
                )
            ) or 0

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

    _CLASS_SORT_COLUMNS = {
        "name": BoatClassORM.name,
        "py_rating": BoatClassORM.py_rating,
        "crew_size": BoatClassORM.crew_size,
        "rya_class_id": BoatClassORM.rya_class_id,
    }

    def list_classes(self, *, limit: int = 50, offset: int = 0,
                     search: Optional[str] = None, hull_type: Optional[str] = None,
                     sort: str = "name", order: str = "asc") -> "list[BoatClassORM]":
        with self.Session() as s:
            q = select(BoatClassORM)
            if search:
                q = q.where(BoatClassORM.name.ilike(f"%{search}%"))
            if hull_type:
                q = q.where(BoatClassORM.hull_type == hull_type)
            column = self._CLASS_SORT_COLUMNS.get(sort, BoatClassORM.name)
            # NULLs (unset py_rating/crew_size on partial rows) always sort last,
            # regardless of direction, instead of leading a descending sort.
            column_ordered = column.desc() if order == "desc" else column.asc()
            q = q.order_by(column.is_(None), column_ordered).limit(limit).offset(offset)
            return list(s.scalars(q).all())

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

    # --- boat_notes (rig-tuning notebook) ---

    def list_notes(self, boat_id: uuid.UUID) -> "list[BoatNoteORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(BoatNoteORM)
                .where(BoatNoteORM.boat_id == boat_id)
                .order_by(BoatNoteORM.position, BoatNoteORM.created_at)
            ).all())

    def get_note(self, boat_id: uuid.UUID, note_id: uuid.UUID) -> Optional[BoatNoteORM]:
        with self.Session() as s:
            return s.scalars(
                select(BoatNoteORM).where(
                    BoatNoteORM.id == note_id, BoatNoteORM.boat_id == boat_id
                )
            ).first()

    def add_note(self, boat_id: uuid.UUID, title: str, body: str) -> BoatNoteORM:
        with self.Session() as s:
            max_position = s.scalar(
                select(func.max(BoatNoteORM.position)).where(BoatNoteORM.boat_id == boat_id)
            )
            position = 0 if max_position is None else max_position + 1
            orm = BoatNoteORM(boat_id=boat_id, title=title, body=body, position=position)
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_note(boat_id, new_id)

    def update_note(self, note_id: uuid.UUID, changes: dict) -> Optional[BoatNoteORM]:
        with self.Session() as s:
            orm = s.get(BoatNoteORM, note_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _NOTE_FIELDS:
                    setattr(orm, k, v)
            s.commit()
            boat_id = orm.boat_id
        return self.get_note(boat_id, note_id)

    def reorder_notes(self, boat_id: uuid.UUID, note_ids: "list[uuid.UUID]") -> bool:
        """Whole-list reorder: succeeds only if ``note_ids`` is exactly the
        boat's current note ids (no missing, no extra, none from another
        boat), assigning position 0..n-1 in submitted order."""
        with self.Session() as s:
            current = list(s.scalars(
                select(BoatNoteORM).where(BoatNoteORM.boat_id == boat_id)
            ).all())
            # Length check too: a duplicated id would pass the set comparison
            # and then leave the list with gaps.
            if len(note_ids) != len(current) or {n.id for n in current} != set(note_ids):
                return False
            by_id = {n.id: n for n in current}
            for position, note_id in enumerate(note_ids):
                by_id[note_id].position = position
            s.commit()
            return True

    def remove_note(self, boat_id: uuid.UUID, note_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.scalars(
                select(BoatNoteORM).where(
                    BoatNoteORM.id == note_id, BoatNoteORM.boat_id == boat_id
                )
            ).first()
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    # --- guest boats + claims (boat_claims) ---

    def clear_guest(self, boat_id: uuid.UUID) -> bool:
        """Drop a boat's placeholder status. Separate from ``update`` because
        ``is_guest`` is not a field a boat edit may touch — only an approved
        claim promotes a guest boat."""
        with self.Session() as s:
            res = s.execute(
                update(BoatORM).where(BoatORM.id == boat_id)
                .values(is_guest=False, guest_created_by=None)
            )
            s.commit()
            return res.rowcount > 0

    def create_claim(self, boat_id: uuid.UUID, *, user_id: uuid.UUID,
                     target_boat_id: Optional[uuid.UUID] = None) -> Optional[BoatClaimORM]:
        """None if this user already has a pending claim on this boat (the
        partial unique index says the same thing; checking first keeps the
        duplicate a caller-visible outcome, like ``add_member``)."""
        with self.Session() as s:
            exists = s.scalars(
                select(BoatClaimORM).where(
                    BoatClaimORM.boat_id == boat_id,
                    BoatClaimORM.user_id == user_id,
                    BoatClaimORM.status == "pending",
                )
            ).first()
            if exists is not None:
                return None
            orm = BoatClaimORM(boat_id=boat_id, user_id=user_id,
                               target_boat_id=target_boat_id, status="pending")
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_claim(new_id)

    def get_claim(self, claim_id: uuid.UUID) -> Optional[BoatClaimORM]:
        with self.Session() as s:
            return s.get(BoatClaimORM, claim_id)

    def list_claims_for_boat(self, boat_id: uuid.UUID, *,
                             status: Optional[str] = None) -> "list[BoatClaimORM]":
        return self._list_claims(BoatClaimORM.boat_id == boat_id, status)

    def list_claims_by_user(self, user_id: uuid.UUID, *,
                            status: Optional[str] = None) -> "list[BoatClaimORM]":
        return self._list_claims(BoatClaimORM.user_id == user_id, status)

    def _list_claims(self, clause, status: Optional[str]) -> "list[BoatClaimORM]":
        with self.Session() as s:
            stmt = select(BoatClaimORM).where(clause)
            if status is not None:
                stmt = stmt.where(BoatClaimORM.status == status)
            return list(s.scalars(stmt.order_by(BoatClaimORM.created_at.desc())).all())

    def resolve_claim(self, claim_id: uuid.UUID, *, status: str,
                      resolved_by: uuid.UUID) -> bool:
        """False if the claim is gone or already resolved — resolving twice
        would otherwise re-run the merge behind it."""
        with self.Session() as s:
            res = s.execute(
                update(BoatClaimORM)
                .where(BoatClaimORM.id == claim_id, BoatClaimORM.status == "pending")
                .values(status=status, resolved_at=datetime.now(timezone.utc),
                        resolved_by=resolved_by)
            )
            s.commit()
            return res.rowcount > 0

    # --- boat merge ---

    def merge_into(self, source_id: uuid.UUID, target_id: uuid.UUID) -> "dict[str, int]":
        """Re-point everything that references the guest boat ``source_id``
        onto ``target_id``, then delete the source row — in ONE transaction,
        because a half-merged boat leaves rows split across two identities
        with no way to tell which side is authoritative.

        Returns per-table counts of what moved (and what was dropped as
        redundant). Note ``sessions.primary_nav_upload_id`` is upload-keyed,
        not boat-keyed, so it is untouched by design."""
        with self.Session() as s:
            source = s.get(BoatORM, source_id)
            if source is None or s.get(BoatORM, target_id) is None:
                raise ValueError("Boat not found")
            moved: "dict[str, int]" = {}

            # Three tables are unique on (parent, boat_id), so a boat entered
            # or scored twice in the same regatta/race would collide on
            # re-point. The target is the authoritative record — it is the one
            # the organizer entered and scored — so the guest's row goes.
            for key, model, sibling in (
                ("regatta_entries", RegattaEntryORM, RegattaEntryORM.regatta_id),
                ("results", ResultORM, ResultORM.race_id),
                ("official_standings", OfficialStandingsORM, OfficialStandingsORM.regatta_id),
            ):
                dropped = s.execute(
                    delete(model).where(
                        model.boat_id == source_id,
                        sibling.in_(select(sibling).where(model.boat_id == target_id)),
                    )
                ).rowcount
                moved[key] = s.execute(
                    update(model).where(model.boat_id == source_id)
                    .values(boat_id=target_id)
                ).rowcount
                if dropped:
                    moved[f"{key}_dropped"] = dropped

            moved["sessions"] = s.execute(
                update(SessionORM).where(SessionORM.boat_id == source_id)
                .values(boat_id=target_id)
            ).rowcount
            moved["devices"] = s.execute(
                update(DeviceORM).where(DeviceORM.owner_boat_id == source_id)
                .values(owner_boat_id=target_id)
            ).rowcount

            # Presence, not data (see the live_recordings gotcha): a heartbeat
            # for a boat that no longer exists is worthless, and the unique
            # (boat_id, user_id) would collide anyway.
            moved["live_recordings_dropped"] = s.execute(
                delete(LiveRecordingORM).where(LiveRecordingORM.boat_id == source_id)
            ).rowcount

            # A boat curve is replaced wholesale by bulk_upsert, so two curves
            # merged into one target would leave contradictory rows in the
            # same (twa, tws) bin. Keep the target's if it has one.
            target_has_curve = s.scalars(
                select(PolarPointORM.id).where(PolarPointORM.boat_id == target_id)
            ).first() is not None
            if target_has_curve:
                moved["polar_points_dropped"] = s.execute(
                    delete(PolarPointORM).where(PolarPointORM.boat_id == source_id)
                ).rowcount
            else:
                moved["polar_points"] = s.execute(
                    update(PolarPointORM).where(PolarPointORM.boat_id == source_id)
                    .values(boat_id=target_id)
                ).rowcount

            moved.update(self._merge_members(s, source_id, target_id))
            moved.update(self._merge_photos_and_notes(s, source_id, target_id))
            moved.update(self._merge_claims(s, source_id, target_id))

            # Every statement above was bulk SQL, so the source's loaded
            # ``members`` collection is stale; expire it or the delete-orphan
            # cascade takes the rows that just moved to the target.
            s.expire(source)
            s.delete(source)
            s.commit()
            return {k: v for k, v in moved.items() if v}

    @staticmethod
    def _merge_members(s, source_id: uuid.UUID, target_id: uuid.UUID) -> "dict[str, int]":
        """user_boats is unique on (user_id, boat_id): someone who is a member
        of both boats keeps the higher of the two roles, and their guest-boat
        row is dropped rather than duplicated.

        Statements, not ORM edits: ``BoatORM.members`` is a delete-orphan
        relationship, so a re-pointed row still sitting in the source's loaded
        collection would be deleted along with the source boat."""
        target_roles = dict(s.execute(
            select(UserBoatORM.user_id, UserBoatORM.role)
            .where(UserBoatORM.boat_id == target_id)
        ).all())
        shared = []
        for user_id, role in s.execute(
            select(UserBoatORM.user_id, UserBoatORM.role)
            .where(UserBoatORM.boat_id == source_id)
        ).all():
            if user_id not in target_roles:
                continue
            shared.append(user_id)
            if _ROLE_RANK[role] > _ROLE_RANK[target_roles[user_id]]:
                s.execute(
                    update(UserBoatORM)
                    .where(UserBoatORM.boat_id == target_id,
                           UserBoatORM.user_id == user_id)
                    .values(role=role)
                )
        if shared:
            s.execute(
                delete(UserBoatORM).where(
                    UserBoatORM.boat_id == source_id,
                    UserBoatORM.user_id.in_(shared),
                )
            )
        moved = s.execute(
            update(UserBoatORM).where(UserBoatORM.boat_id == source_id)
            .values(boat_id=target_id)
        ).rowcount
        return {"members": moved, "members_dropped": len(shared)}

    @staticmethod
    def _merge_photos_and_notes(s, source_id: uuid.UUID,
                                target_id: uuid.UUID) -> "dict[str, int]":
        # boat_photos is unique on (boat_id, image_id) — the same picture
        # already linked to the target is just a duplicate link.
        taken = select(BoatPhotoORM.image_id).where(BoatPhotoORM.boat_id == target_id)
        s.execute(
            delete(BoatPhotoORM).where(
                BoatPhotoORM.boat_id == source_id,
                BoatPhotoORM.image_id.in_(taken),
            )
        )
        photos = s.execute(
            update(BoatPhotoORM).where(BoatPhotoORM.boat_id == source_id)
            .values(boat_id=target_id)
        ).rowcount

        # Notes land after the target's own, so its notebook keeps its order.
        offset = s.scalar(
            select(func.max(BoatNoteORM.position)).where(BoatNoteORM.boat_id == target_id)
        )
        offset = 0 if offset is None else offset + 1
        notes = s.execute(
            update(BoatNoteORM).where(BoatNoteORM.boat_id == source_id)
            .values(boat_id=target_id, position=BoatNoteORM.position + offset)
        ).rowcount
        return {"photos": photos, "notes": notes}

    @staticmethod
    def _merge_claims(s, source_id: uuid.UUID, target_id: uuid.UUID) -> "dict[str, int]":
        """Claims *on* the guest boat are moot once it is gone — including the
        rival pending ones — so they are deleted, not resolved: an approved
        claim is a decision somebody made, and inventing one here would put a
        resolution nobody took into the record.

        A claim pointing *at* the guest boat as its merge target follows the
        merge instead, unless that would make it target its own subject (the
        target_boat_not_self CHECK), in which case it is moot too."""
        dropped = s.execute(
            delete(BoatClaimORM).where(
                or_(BoatClaimORM.boat_id == source_id,
                    (BoatClaimORM.target_boat_id == source_id)
                    & (BoatClaimORM.boat_id == target_id)),
            )
        ).rowcount
        retargeted = s.execute(
            update(BoatClaimORM).where(BoatClaimORM.target_boat_id == source_id)
            .values(target_boat_id=target_id)
        ).rowcount
        return {"claims_dropped": dropped, "claims_retargeted": retargeted}
