"""Drop ``session_maneuvers.max_heel_deg`` — moved into the ``features`` JSON
column (added in 0015) as ``features["max_heel_deg"]``.

Rationale: heel characterizes the maneuver itself (like the other statistics
in ``features``), not the specific occurrence's position/timing (which stay as
their own columns — ``start_time``, ``start_lat``/``start_lon``, etc.). See
``workers/process_upload/processing/maneuver_features.py::_max_heel_deg``.

No backfill: existing ``max_heel_deg`` values are not migrated into
``features`` for already-persisted rows — they are dropped. Sessions get the
value back in ``features`` the next time they're (re)analyzed.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0016'
down_revision: Union[str, None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('session_maneuvers', 'max_heel_deg')


def downgrade() -> None:
    op.add_column('session_maneuvers', sa.Column('max_heel_deg', sa.Float(), nullable=True))
