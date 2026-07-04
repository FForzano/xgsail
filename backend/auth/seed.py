"""Default seeds: RBAC permissions/roles, device types, bootstrap superadmin.

Idempotent — safe to run on every startup. Roles and their permission sets are
data, so deployments can add/adjust roles afterwards without code changes.

Superadmin is a flag on ``users`` (``is_superadmin``, bypasses every check in
``_user_has_permission``), NOT a role row — only the two club-scoped
institutional roles from docs/api-project.md are seeded.
"""

import os

from sqlalchemy import select

from .passwords import hash_password

# permission key -> human description (see docs/api-project.md, "Ruoli e
# permessi per classe di API")
DEFAULT_PERMISSIONS = {
    "club.manage": "Update/deactivate a club",
    "user_club.manage": "Approve/remove club memberships",
    "user_role.manage_scoped": "Grant club-scoped roles (never superadmin)",
    "regatta.manage": "CRUD regattas",
    "raceday.manage": "CRUD race days",
    "race.manage": "CRUD races",
    "result.manage": "CRUD race results",
    "mark.manage": "CRUD marks for race activities",
    "activity.manage": "Manage club-linked activities and their marks",
}

_RACE_OFFICER_KEYS = [
    "regatta.manage",
    "raceday.manage",
    "race.manage",
    "result.manage",
    "mark.manage",
    "activity.manage",
]

# role name -> (description, [permission keys])
DEFAULT_ROLES = {
    "club_admin": ("Administrator within a club", list(DEFAULT_PERMISSIONS)),
    "race_officer": ("Runs regattas/races for a club", _RACE_OFFICER_KEYS),
}

# name -> (category, parser_key)
DEFAULT_DEVICE_TYPES = {
    "SailFrames E1": ("boat_tracker", "sailframes_e1_csv"),
    "Generic GPX": ("boat_tracker", "generic_gpx"),
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


def seed_device_types(session_factory) -> None:
    """Seed the device-type catalog the claim flow picks from. Idempotent —
    matches on unique name, never touches existing rows."""
    from ..db.models import DeviceTypeORM

    with session_factory() as s:
        for name, (category, parser_key) in DEFAULT_DEVICE_TYPES.items():
            existing = s.scalars(
                select(DeviceTypeORM).where(DeviceTypeORM.name == name)
            ).first()
            if existing is None:
                s.add(DeviceTypeORM(name=name, category=category, parser_key=parser_key))
        s.commit()


def seed_superadmin(repos) -> None:
    """Bootstrap the superadmin from env, via the user repo. Idempotent: no-op
    if the user already exists or no email is configured."""
    admin_email = os.environ.get("SAILFRAMES_SUPERADMIN_EMAIL")
    if not admin_email:
        return
    admin_email = admin_email.strip().lower()
    if repos.users.get_by_email(admin_email) is not None:
        return
    admin_password = os.environ.get("SAILFRAMES_SUPERADMIN_PASSWORD")
    repos.users.create(
        email=admin_email,
        password_hash=hash_password(admin_password) if admin_password else None,
        first_name="Super",
        last_name="Admin",
        terms_and_conditions=True,
        is_active=True,
        is_superadmin=True,
    )
