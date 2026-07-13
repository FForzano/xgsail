"""Add ``session_maneuvers.original_maneuver_type`` + ``corrected_by_user``
so a user correcting a detected maneuver's type (tack/gybe/course_change) is
distinguishable from the pipeline's own classification — the provenance
signal the maneuver-classifier training set needs (see
scripts/export_maneuver_training_data.py and
workers/train_maneuver/README.md).

``original_maneuver_type`` is backfilled from ``maneuver_type`` for existing
rows (nothing has been corrected yet, so they're identical by definition),
then set NOT NULL. ``corrected_by_user`` defaults false.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0017'
down_revision: Union[str, None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('session_maneuvers', sa.Column('original_maneuver_type', sa.String(), nullable=True))
    op.execute('UPDATE session_maneuvers SET original_maneuver_type = maneuver_type')
    op.alter_column('session_maneuvers', 'original_maneuver_type', nullable=False)
    op.create_check_constraint(
        'original_maneuver_type_allowed', 'session_maneuvers',
        "original_maneuver_type IN ('tack', 'gybe', 'course_change')",
    )

    op.add_column(
        'session_maneuvers',
        sa.Column('corrected_by_user', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('session_maneuvers', 'corrected_by_user', server_default=None)


def downgrade() -> None:
    op.drop_column('session_maneuvers', 'corrected_by_user')
    op.drop_constraint('original_maneuver_type_allowed', 'session_maneuvers', type_='check')
    op.drop_column('session_maneuvers', 'original_maneuver_type')
