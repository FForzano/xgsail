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
        UserORM,
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

        # Optional bootstrap superadmin from env.
        admin_email = os.environ.get("SAILFRAMES_SUPERADMIN_EMAIL")
        admin_password = os.environ.get("SAILFRAMES_SUPERADMIN_PASSWORD")
        if admin_email:
            user = s.scalars(select(UserORM).where(UserORM.email == admin_email)).first()
            if user is None:
                s.add(UserORM(
                    email=admin_email,
                    password_hash=hash_password(admin_password) if admin_password else None,
                    name="Superadmin",
                    is_active=True,
                    is_superadmin=True,
                    created_at=datetime.now(timezone.utc).isoformat(),
                ))

        s.commit()
