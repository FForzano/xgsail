"""``session_analysis.unavailable_reason`` — why a session has no
wind-dependent analysis.

A session sailed with no onboard wind sensor and no station/model wind at all
gets no maneuvers/legs/polar/VMG/true wind: the worker refuses rather than
guess, and posts ``analysis_unavailable`` instead. Without a stored reason the
user saw an empty analysis indistinguishable from a broken one.

Nullable, NULL being the normal case, and no backfill: every row written
before this revision came from a worker that always attempted the analysis.

Revision ID: 0064
Revises: 0063
Create Date: 2026-09-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0064'
down_revision: Union[str, None] = '0063'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('session_analysis',
                  sa.Column('unavailable_reason', sa.String(), nullable=True))
    op.create_check_constraint('unavailable_reason_allowed', 'session_analysis',
                               "unavailable_reason IN ('no_wind_data')")


def downgrade() -> None:
    op.drop_constraint('unavailable_reason_allowed', 'session_analysis', type_='check')
    op.drop_column('session_analysis', 'unavailable_reason')
