"""Object-storage device repository — ``meta/devices.json``.

Assignments are nested inside each device record. Overlap validation and the
boat-resolution order live in ``domain.device`` so they match the SQL backend
exactly.
"""

from typing import Optional

from ... import domain
from ...domain.device import windows_overlap, resolve_boat_from
from ...storage import BlobStore
from ..base import DeviceRepo
from ._common import DEVICES_INDEX_KEY, load_index, next_int_id


class ObjectDeviceRepo(DeviceRepo):
    def __init__(self, blob: BlobStore):
        self.blob = blob

    def _load(self) -> list[dict]:
        return load_index(self.blob, DEVICES_INDEX_KEY).get("devices", [])

    def _save(self, devices: list[dict]) -> None:
        self.blob.put_json(DEVICES_INDEX_KEY, {"devices": devices})

    def list(self) -> list[domain.Device]:
        return [domain.Device.from_dict(d) for d in self._load()]

    def get(self, device_id: str) -> Optional[domain.Device]:
        for d in self._load():
            if d.get("device_id") == device_id:
                return domain.Device.from_dict(d)
        return None

    def register(self, device: domain.Device) -> domain.Device:
        devices = self._load()
        for i, d in enumerate(devices):
            if d.get("device_id") == device.device_id:
                devices[i] = device.to_dict()
                break
        else:
            devices.append(device.to_dict())
        self._save(devices)
        return device

    def add_assignment(self, assignment: domain.DeviceAssignment) -> domain.DeviceAssignment:
        devices = self._load()
        for d in devices:
            if d.get("device_id") == assignment.device_id:
                existing = d.setdefault("assignments", [])
                for e in existing:
                    if windows_overlap(
                        assignment.valid_from, assignment.valid_to,
                        e.get("valid_from"), e.get("valid_to"),
                    ):
                        raise ValueError("Assignment window overlaps an existing one")
                assignment.id = next_int_id(existing)
                existing.append(assignment.to_dict())
                self._save(devices)
                return assignment
        raise ValueError(f"Unknown device: {assignment.device_id}")

    def list_assignments(self, device_id: str) -> "list[domain.DeviceAssignment]":
        dev = self.get(device_id)
        return dev.assignments if dev else []

    def resolve_boat(self, device_id: str, at_iso: str) -> Optional[str]:
        dev = self.get(device_id)
        return resolve_boat_from(dev, at_iso) if dev else None

    def touch_last_seen(self, device_id: str, at_iso: str) -> bool:
        devices = self._load()
        for d in devices:
            if d.get("device_id") == device_id:
                d["last_seen_at"] = at_iso
                self._save(devices)
                return True
        return False
