"""Default RBAC seed: permissions, roles, and an optional bootstrap superadmin.

Idempotent — safe to run on every startup. Roles and their permission sets are
data, so deployments can add/adjust roles afterwards without code changes.
"""

import os
from datetime import datetime, timezone

from sqlalchemy import select

from .passwords import hash_password

# permission key -> human description
DEFAULT_PERMISSIONS = {
    "admin": "Full administrative access",
    "regatta.manage": "Create/edit/delete regattas",
    "raceday.manage": "Create/edit/delete race days",
    "race.create": "Create races",
    "race.edit": "Edit races",
    "race.delete": "Delete races",
    "boat.edit": "Edit the boat catalog",
    "session.delete": "Delete sessions",
    "user.manage": "Manage users and roles",
}

# role name -> (description, [permission keys])
DEFAULT_ROLES = {
    "software_admin": ("Global software administrator", list(DEFAULT_PERMISSIONS.keys())),
    "club_admin": (
        "Administrator within a club",
        ["regatta.manage", "raceday.manage", "race.create", "race.edit",
         "race.delete", "boat.edit", "session.delete"],
    ),
    "race_officer": (
        "Runs races for a club",
        ["raceday.manage", "race.create", "race.edit"],
    ),
    "member": ("Regular member (read-only)", []),
}


def seed_defaults(session_factory) -> None:
    from ..db.models import (
        PermissionORM,
        RoleORM,
        RolePermissionORM,
    )

    with session_factory() as s:
        # Permissions
        perms = {}
        for key, desc in DEFAULT_PERMISSIONS.items():
            p = s.scalars(select(PermissionORM).where(PermissionORM.key == key)).first()
            if p is None:
                p = PermissionORM(key=key, description=desc)
                s.add(p)
                s.flush()
            perms[key] = p

        # Roles + their permission grants
        for name, (desc, keys) in DEFAULT_ROLES.items():
            role = s.scalars(select(RoleORM).where(RoleORM.name == name)).first()
            if role is None:
                role = RoleORM(name=name, description=desc)
                s.add(role)
                s.flush()
            existing = {rp.permission_id for rp in role.permissions}
            for key in keys:
                pid = perms[key].id
                if pid not in existing:
                    s.add(RolePermissionORM(role_id=role.id, permission_id=pid))

        s.commit()


# The real physical fleet (the only concrete devices we have). Mirrors the
# `const BOATS` list in web/fleet.html. No fictional B* units.
FLEET_DEVICE_IDS = ["E1", "E2", "E3", "E4", "E5", "E6"]


def seed_devices(repos) -> None:
    """Register the physical E1–E6 fleet in the device registry on both
    metadata backends. Idempotent — skips devices that already exist, so it
    never clobbers a hand-edited default_boat_id / assignment."""
    for device_id in FLEET_DEVICE_IDS:
        if repos.devices.get(device_id) is not None:
            continue
        from .. import domain

        repos.devices.register(domain.Device(
            device_id=device_id,
            name=device_id,
            device_type="sailframes_e",
            owner_type="club",
            status="active",
            created_at=datetime.now(timezone.utc).isoformat(),
        ))


def seed_superadmin(repos) -> None:
    """Backend-agnostic bootstrap superadmin from env, via the user repo.

    Runs on both metadata backends (the RBAC role/permission seed above is
    Postgres-only, but a login identity must exist in object mode too).
    Idempotent: no-op if the user already exists or no email is configured.
    """
    admin_email = os.environ.get("SAILFRAMES_SUPERADMIN_EMAIL")
    if not admin_email:
        return
    admin_email = admin_email.strip().lower()
    if repos.users.get_by_email(admin_email) is not None:
        return
    from .. import domain

    admin_password = os.environ.get("SAILFRAMES_SUPERADMIN_PASSWORD")
    repos.users.create(
        domain.User(
            email=admin_email,
            name="Superadmin",
            is_active=True,
            is_superadmin=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        ),
        hash_password(admin_password) if admin_password else None,
    )
