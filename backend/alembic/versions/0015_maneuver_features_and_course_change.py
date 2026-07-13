"""Add ``session_maneuvers.features`` (JSON) and allow the ``course_change``
maneuver type.

``features`` persists the statistical feature vector computed at detection
(see ``workers/process_upload/processing/maneuver_features.py``) so a training
dataset for the future ML maneuver classifier accumulates from real sessions.

The ``maneuver_type`` CHECK is widened from ``('tack','gybe')`` to also allow
``'course_change'`` — the third class the ML classifier will predict. No row
carries it yet (the active geometric classifier only emits tack/gybe), so the
downgrade safely narrows the CHECK back.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0015'
down_revision: Union[str, None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('session_maneuvers', sa.Column('features', sa.JSON(), nullable=True))
    # CHECK constraints can't be altered in place — drop and recreate.
    op.drop_constraint('maneuver_type_allowed', 'session_maneuvers', type_='check')
    op.create_check_constraint(
        'maneuver_type_allowed', 'session_maneuvers',
        "maneuver_type IN ('tack', 'gybe', 'course_change')",
    )


def downgrade() -> None:
    op.drop_constraint('maneuver_type_allowed', 'session_maneuvers', type_='check')
    op.create_check_constraint(
        'maneuver_type_allowed', 'session_maneuvers',
        "maneuver_type IN ('tack', 'gybe')",
    )
    op.drop_column('session_maneuvers', 'features')
