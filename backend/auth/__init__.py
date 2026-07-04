"""Authentication & authorization for the SailFrames API.

Principals and guards (see docs/api-project.md, "Ruoli e permessi"):
- ``require_user`` / ``current_user`` — cookie-JWT users.
- ``require_permission`` (scoped RBAC, raising) and ``user_has_permission``
  (non-raising, for "ownership OR permission" guards).
- ``require_superadmin`` — the ``users.is_superadmin`` flag gate.
- ``current_device`` / ``require_system`` (device.py) — DeviceKey-authenticated
  hardware and hook-token system callers.
- Visibility rules: ``activity_visible_to`` / ``session_visible_to`` /
  ``can_edit_activity``.
"""

from .permissions import (
    require_permission,
    user_has_permission,
    require_superadmin,
    current_user,
    require_user,
    verify_csrf,
    activity_visible_to,
    session_visible_to,
    can_edit_activity,
    effective_capabilities,
)
from .device import current_device, require_system
from .passwords import hash_password, verify_password
from .seed import seed_defaults, seed_superadmin, seed_device_types

__all__ = [
    "require_permission",
    "user_has_permission",
    "require_superadmin",
    "current_user",
    "require_user",
    "verify_csrf",
    "activity_visible_to",
    "session_visible_to",
    "can_edit_activity",
    "effective_capabilities",
    "current_device",
    "require_system",
    "hash_password",
    "verify_password",
    "seed_defaults",
    "seed_superadmin",
    "seed_device_types",
]
