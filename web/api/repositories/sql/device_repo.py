"""SQL device repository (+ attribution windows)."""

from typing import Optional

from sqlalchemy import select, update

from ... import domain
from ...domain.device import windows_overlap, resolve_boat_from
from ...db.models import DeviceORM, DeviceAssignmentORM
from ..base import DeviceRepo
from . import _mappers as M


class SqlDeviceRepo(DeviceRepo):
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self) -> list[domain.Device]:
        with self.Session() as s:
            return [M.device_to_domain(d) for d in s.scalars(select(DeviceORM)).all()]

    def get(self, device_id: str) -> Optional[domain.Device]:
        with self.Session() as s:
            orm = s.get(DeviceORM, device_id)
            return M.device_to_domain(orm) if orm else None

    def register(self, device: domain.Device) -> domain.Device:
        with self.Session() as s:
            orm = s.get(DeviceORM, device.device_id)
            if orm is None:
                orm = DeviceORM(device_id=device.device_id)
                s.add(orm)
            orm.name = device.name
            orm.device_type = device.device_type
            orm.default_boat_id = device.default_boat_id
            orm.owner_type = device.owner_type
            orm.registered_by = device.registered_by
            orm.owned_by_club_id = device.owned_by_club_id
            orm.status = device.status
            orm.created_at = device.created_at
            orm.last_seen_at = device.last_seen_at
            s.commit()
            return device

    def add_assignment(self, assignment: domain.DeviceAssignment) -> domain.DeviceAssignment:
        with self.Session() as s:
            if s.get(DeviceORM, assignment.device_id) is None:
                raise ValueError(f"Unknown device: {assignment.device_id}")
            existing = s.scalars(
                select(DeviceAssignmentORM).where(
                    DeviceAssignmentORM.device_id == assignment.device_id
                )
            ).all()
            for e in existing:
                if windows_overlap(
                    assignment.valid_from, assignment.valid_to, e.valid_from, e.valid_to
                ):
                    raise ValueError("Assignment window overlaps an existing one")
            orm = DeviceAssignmentORM(
                device_id=assignment.device_id,
                boat_id=assignment.boat_id,
                regatta_id=assignment.regatta_id,
                race_id=assignment.race_id,
                valid_from=assignment.valid_from,
                valid_to=assignment.valid_to,
                created_by=assignment.created_by,
                created_at=assignment.created_at,
            )
            s.add(orm)
            s.commit()
            assignment.id = orm.id
            return assignment

    def list_assignments(self, device_id: str) -> "list[domain.DeviceAssignment]":
        with self.Session() as s:
            rows = s.scalars(
                select(DeviceAssignmentORM).where(
                    DeviceAssignmentORM.device_id == device_id
                )
            ).all()
            return [M.assignment_to_domain(r) for r in rows]

    def resolve_boat(self, device_id: str, at_iso: str) -> Optional[str]:
        dev = self.get(device_id)
        return resolve_boat_from(dev, at_iso) if dev else None

    def touch_last_seen(self, device_id: str, at_iso: str) -> bool:
        with self.Session() as s:
            res = s.execute(
                update(DeviceORM)
                .where(DeviceORM.device_id == device_id)
                .values(last_seen_at=at_iso)
            )
            s.commit()
            return res.rowcount > 0
