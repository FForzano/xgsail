"""``boat_claims``: the real owner asking to take over a guest boat.

A guest boat (``boats.is_guest``, see ``boat.py``) is a placeholder created by
someone else, and boat membership gates session read access — so a claim is a
request the guest boat's creator approves or rejects, never an instant grant.
``target_boat_id`` names the claimant's own boat to merge the guest into; NULL
means promote the guest boat itself.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, UUIDPKMixin, enum_check

BOAT_CLAIM_STATUSES = ("pending", "approved", "rejected")


class BoatClaimORM(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "boat_claims"
    __table_args__ = (
        # Partial rather than plain unique: one *open* claim per person per
        # boat, while re-claiming after a rejection stays possible.
        Index(
            "uq_boat_claims_boat_user_pending",
            "boat_id", "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        CheckConstraint(
            "target_boat_id IS NULL OR target_boat_id <> boat_id",
            name="target_boat_not_self",
        ),
        enum_check("status", BOAT_CLAIM_STATUSES),
    )

    boat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("boats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_boat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("boats.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
