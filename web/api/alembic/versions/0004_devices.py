"""Phase 4 — device registry (devices + device_assignments)

Adds the tracker registry (``devices``, PK = ``device_id`` string) and the
bounded boat-attribution windows (``device_assignments``). Explicit
``op.create_table`` on top of the frozen baseline chain (see 0001–0003).

Revision ID: 0004_devices
Revises: 0003_groups
Create Date: 2026-07-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_devices"
down_revision: Union[str, None] = "0003_groups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("device_type", sa.String(), nullable=False),
        sa.Column("default_boat_id", sa.String(), nullable=True),
        sa.Column("owner_type", sa.String(), nullable=False),
        sa.Column("registered_by", sa.Integer(), nullable=True),
        sa.Column("owned_by_club_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("last_seen_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["default_boat_id"], ["boats.boat_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["registered_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owned_by_club_id"], ["clubs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_table(
        "device_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("boat_id", sa.String(), nullable=False),
        sa.Column("regatta_id", sa.String(), nullable=True),
        sa.Column("race_id", sa.String(), nullable=True),
        sa.Column("valid_from", sa.String(), nullable=True),
        sa.Column("valid_to", sa.String(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_device_assignments_device_id", "device_assignments", ["device_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_device_assignments_device_id", table_name="device_assignments")
    op.drop_table("device_assignments")
    op.drop_table("devices")
