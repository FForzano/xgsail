"""Add ``session_maneuvers.source``, ``rejected``, ``pending`` — lets a user
reject a false-positive detection or add a maneuver the algorithm missed,
and lets both (plus an existing ``PATCH .../maneuvers/{id}`` type
correction) survive a reanalysis instead of being silently wiped by the
next full-replace (see ``session_repo.py::upsert_maneuvers`` and the new
``services/maneuver_reconciliation.py``).

- ``source``: 'detected' (pipeline output, backfilled for all existing
  rows) or 'manual' (user-added). Nullable during backfill, then NOT NULL.
- ``rejected``: user said "not a real maneuver" — tombstone flag, not a
  delete, so a later reanalysis can't resurrect it as a fresh row.
- ``pending``: true only for a manual row between creation and the
  worker's async stat computation landing.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0018'
down_revision: Union[str, None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('session_maneuvers', sa.Column('source', sa.String(), nullable=True))
    op.execute("UPDATE session_maneuvers SET source = 'detected'")
    op.alter_column('session_maneuvers', 'source', nullable=False)
    op.create_check_constraint(
        'source_allowed', 'session_maneuvers',
        "source IN ('detected', 'manual')",
    )

    op.add_column(
        'session_maneuvers',
        sa.Column('rejected', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('session_maneuvers', 'rejected', server_default=None)

    op.add_column(
        'session_maneuvers',
        sa.Column('pending', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('session_maneuvers', 'pending', server_default=None)


def downgrade() -> None:
    op.drop_column('session_maneuvers', 'pending')
    op.drop_column('session_maneuvers', 'rejected')
    op.drop_constraint('source_allowed', 'session_maneuvers', type_='check')
    op.drop_column('session_maneuvers', 'source')
