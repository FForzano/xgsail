"""SQL device repository: ``device_types`` catalog + ``devices`` registry.

Devices are registered self-service via the claim flow (docs/api-project.md,
"Registrazione device"): ``create_claim`` mints a short-lived ``claim_code``,
``confirm_claim`` binds the hardware ``external_id`` and stores the hash of the
one-time ``device_api_key``. Lookup hot paths: ``get_by_api_key_hash`` (every
DeviceKey-authenticated call) and ``get_claimed_by_external_id`` (legacy E1
webhook attribution).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_, select

from ...db.models import DeviceORM, DeviceTypeORM


class SqlDeviceRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    # --- device_types catalog ---

    def list_types(self) -> "list[DeviceTypeORM]":
        with self.Session() as s:
            return list(s.scalars(select(DeviceTypeORM)).all())

    def get_type(self, type_id: uuid.UUID) -> Optional[DeviceTypeORM]:
        with self.Session() as s:
            return s.get(DeviceTypeORM, type_id)

    def create_type(self, data: dict) -> DeviceTypeORM:
        with self.Session() as s:
            orm = DeviceTypeORM(**data)
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_type(new_id)

    def update_type(self, type_id: uuid.UUID, changes: dict) -> Optional[DeviceTypeORM]:
        with self.Session() as s:
            orm = s.get(DeviceTypeORM, type_id)
            if orm is None:
                return None
            for k, v in changes.items():
                setattr(orm, k, v)
            s.commit()
        return self.get_type(type_id)

    def delete_type(self, type_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(DeviceTypeORM, type_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    # --- devices ---

    def list(self, *, owner_user_id: Optional[uuid.UUID] = None,
             owner_boat_ids: Optional[list] = None,
             owner_club_ids: Optional[list] = None) -> "list[DeviceORM]":
        """List devices by ownership. With no filters returns everything
        (superadmin view); otherwise the union of the given owners."""
        with self.Session() as s:
            q = select(DeviceORM)
            clauses = []
            if owner_user_id is not None:
                clauses.append(DeviceORM.owner_user_id == owner_user_id)
            if owner_boat_ids:
                clauses.append(DeviceORM.owner_boat_id.in_(owner_boat_ids))
            if owner_club_ids:
                clauses.append(DeviceORM.owner_club_id.in_(owner_club_ids))
            if clauses:
                q = q.where(or_(*clauses))
            return list(s.scalars(q).all())

    def get(self, device_id: uuid.UUID) -> Optional[DeviceORM]:
        with self.Session() as s:
            return s.get(DeviceORM, device_id)

    def get_claimed_by_external_id(self, external_id: str) -> Optional[DeviceORM]:
        with self.Session() as s:
            return s.scalars(
                select(DeviceORM).where(
                    DeviceORM.external_id == external_id,
                    DeviceORM.status == "claimed",
                )
            ).first()

    def get_by_claim_code(self, claim_code: str) -> Optional[DeviceORM]:
        """Unclaimed row matching the code — expiry is NOT checked here so the
        claim endpoint can answer 404 (unknown) vs 409 (expired) per the
        protocol's error table."""
        with self.Session() as s:
            return s.scalars(
                select(DeviceORM).where(
                    DeviceORM.claim_code == claim_code,
                    DeviceORM.status == "unclaimed",
                )
            ).first()

    def get_by_api_key_hash(self, api_key_hash: str) -> Optional[DeviceORM]:
        with self.Session() as s:
            return s.scalars(
                select(DeviceORM).where(
                    DeviceORM.api_key_hash == api_key_hash,
                    DeviceORM.status == "claimed",
                )
            ).first()

    def create_claim(self, *, device_type_id: uuid.UUID, nickname: Optional[str],
                     owner_user_id: Optional[uuid.UUID],
                     owner_boat_id: Optional[uuid.UUID],
                     owner_club_id: Optional[uuid.UUID],
                     claim_code: str, expires_at: datetime) -> DeviceORM:
        """Create (or refresh) an unclaimed device row for a claim target.

        If an unclaimed row already exists for the exact same target, its
        claim code/expiry is refreshed instead of inserting a duplicate."""
        def _eq(col, val):
            return col == val if val is not None else col.is_(None)

        with self.Session() as s:
            existing = s.scalars(
                select(DeviceORM).where(
                    DeviceORM.status == "unclaimed",
                    DeviceORM.device_type_id == device_type_id,
                    _eq(DeviceORM.owner_user_id, owner_user_id),
                    _eq(DeviceORM.owner_boat_id, owner_boat_id),
                    _eq(DeviceORM.owner_club_id, owner_club_id),
                )
            ).first()
            if existing is not None:
                existing.claim_code = claim_code
                existing.claim_code_expires_at = expires_at
                if nickname is not None:
                    existing.nickname = nickname
                s.commit()
                new_id = existing.id
            else:
                orm = DeviceORM(
                    device_type_id=device_type_id,
                    nickname=nickname,
                    owner_user_id=owner_user_id,
                    owner_boat_id=owner_boat_id,
                    owner_club_id=owner_club_id,
                    status="unclaimed",
                    claim_code=claim_code,
                    claim_code_expires_at=expires_at,
                )
                s.add(orm)
                s.commit()
                new_id = orm.id
        return self.get(new_id)

    def confirm_claim(self, device_id: uuid.UUID, *, external_id: str,
                      api_key_hash: str, claimed_by: uuid.UUID) -> Optional[DeviceORM]:
        with self.Session() as s:
            orm = s.get(DeviceORM, device_id)
            if orm is None:
                return None
            orm.external_id = external_id
            orm.status = "claimed"
            orm.claimed_at = datetime.now(timezone.utc)
            orm.claimed_by = claimed_by
            orm.api_key_hash = api_key_hash
            orm.claim_code = None
            orm.claim_code_expires_at = None
            s.commit()
        return self.get(device_id)

    def set_api_key_hash(self, device_id: uuid.UUID, api_key_hash: str) -> bool:
        with self.Session() as s:
            orm = s.get(DeviceORM, device_id)
            if orm is None or orm.status != "claimed":
                return False
            orm.api_key_hash = api_key_hash
            s.commit()
            return True

    def update(self, device_id: uuid.UUID, changes: dict) -> Optional[DeviceORM]:
        allowed = ("nickname", "owner_user_id", "owner_boat_id", "owner_club_id")
        with self.Session() as s:
            orm = s.get(DeviceORM, device_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in allowed:
                    setattr(orm, k, v)
            s.commit()
        return self.get(device_id)

    def revoke(self, device_id: uuid.UUID) -> bool:
        """Revoke a device: its key stops being accepted immediately."""
        with self.Session() as s:
            orm = s.get(DeviceORM, device_id)
            if orm is None:
                return False
            orm.status = "revoked"
            orm.api_key_hash = None
            orm.claim_code = None
            s.commit()
            return True
