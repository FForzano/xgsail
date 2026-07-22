"""Third-party wearable-cloud account links (``integration_connections``).

Scaffolding only — see `backend/routers/integrations.py`: the router that
uses this table currently returns 503 "coming soon" for every provider.
Modeled ahead of time so the frontend's "in arrivo" device picker cards
(Garmin, Polar) map to a real (if inert) API surface rather than nothing.

One row per (user, provider): a user connects their own Garmin/Polar account
via OAuth, and activities pulled from that provider land as regular
``session_upload``s through the server-side ingest seam
(``services/ingestion.register_gps_stream`` / ``stage_raw_upload``) — the
same seam manual GPX/CSV imports use, see docs/device-protocol.md §8 for the
adjacent (but separate) BLE-relay transport for XGSail's own hardware.

Token fields are deliberately typed for encrypted storage (`String`, no
length assumption baked in) but nothing encrypts/decrypts them yet — that
lands with the first real provider integration, not with this scaffold.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDPKMixin, enum_check

INTEGRATION_PROVIDERS = ("garmin", "polar")
INTEGRATION_STATUSES = ("pending", "active", "revoked", "error")


class IntegrationConnectionORM(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        enum_check("provider", INTEGRATION_PROVIDERS),
        enum_check("status", INTEGRATION_STATUSES),
        UniqueConstraint("user_id", "provider", name="one_connection_per_user_provider"),
    )
    __wire_exclude__ = ("access_token", "refresh_token")

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # The provider's own id for this athlete/user — needed to correlate
    # webhook/poll payloads back to a connection.
    external_athlete_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Encrypted at rest once a real provider lands (see module docstring).
    access_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scopes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
