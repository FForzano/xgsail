"""Phase 5 — session privacy/attribution columns + session_crew

Adds the owner/boat_id/visibility/club/group/regatta/race columns to
``sessions`` and the ``session_crew`` table (the actual crew of an outing,
distinct from a boat's standing ``boat_members``). Uses ``batch_alter_table``
for the column adds so the same revision runs on Postgres and on the SQLite
stand-in used by tests. ``visibility`` gets a ``server_default='private'`` so
any pre-existing rows are valid; new inserts set it explicitly.

Revision ID: 0005_session_privacy
Revises: 0004_devices
Create Date: 2026-07-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_session_privacy"
down_revision: Union[str, None] = "0004_devices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("boat_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("visibility", sa.String(), nullable=False, server_default="private")
        )
        batch_op.add_column(sa.Column("club_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("group_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("regatta_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("race_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_sessions_owner_user_id", "users", ["owner_user_id"], ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_sessions_club_id", "clubs", ["club_id"], ["id"], ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_sessions_group_id", "groups", ["group_id"], ["id"], ondelete="SET NULL",
        )

    op.create_table(
        "session_crew",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("guest_name", sa.String(), nullable=True),
        sa.Column("boat_role", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_crew_session_id", "session_crew", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_session_crew_session_id", table_name="session_crew")
    op.drop_table("session_crew")
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_sessions_group_id", type_="foreignkey")
        batch_op.drop_constraint("fk_sessions_club_id", type_="foreignkey")
        batch_op.drop_constraint("fk_sessions_owner_user_id", type_="foreignkey")
        batch_op.drop_column("race_id")
        batch_op.drop_column("regatta_id")
        batch_op.drop_column("group_id")
        batch_op.drop_column("club_id")
        batch_op.drop_column("visibility")
        batch_op.drop_column("boat_id")
        batch_op.drop_column("owner_user_id")
