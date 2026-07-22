"""Account tables: ``users`` and ``auth_refresh_tokens``.

RBAC grants live in ``rbac.py`` (roles/permissions/user_roles); memberships in
``club.py``/``group.py``/``boat.py``. See ``backend/auth`` for how tokens and
permissions are evaluated.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDPKMixin, enum_check

USER_STATUSES = ("inactive", "active", "deleted")
USER_UNIT_SYSTEMS = ("nautical", "metric")


class UserORM(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        enum_check("status", USER_STATUSES),
        enum_check("unit_system", USER_UNIT_SYSTEMS),
    )
    # Secrets never leave the repo on the wire.
    __wire_exclude__ = ("password_hash", "password_reset_token")

    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dob: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    terms_and_conditions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Versioned legal acceptance: which version of each document the user last
    # accepted, and when. NULL/"legacy" (vs the current version in
    # backend/legal.py) means the user must (re-)accept before using the app —
    # see the capabilities `legal.needs_acceptance` flag. Terms and Privacy are
    # tracked separately: they are distinct documents with distinct acceptances
    # (GDPR consent can't be bundled into the terms acceptance).
    terms_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    privacy_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    privacy_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # use_alter breaks the users<->images FK cycle (images.created_by -> users):
    # this FK is added with a separate ALTER after both tables exist.
    profile_image_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    unit_system: Mapped[str] = mapped_column(String, nullable=False, default="nautical")
    password_reset_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # "Buy Me a Coffee" in-app reminder (see auth/permissions.py::_support_status).
    # NULL next_at means "never shown yet" — the default 30-day-from-registration
    # threshold applies. Tracked server-side (not localStorage) so the cadence
    # survives across devices/reinstalls.
    support_prompt_next_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    support_donated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list["UserRoleORM"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class AuthRefreshTokenORM(UUIDPKMixin, Base):
    """One row per issued refresh token. Rotation chains via family_id/prev_id;
    only the hash of the opaque token is stored, never its plaintext value."""

    __tablename__ = "auth_refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    prev_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("auth_refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True)
