"""Add ``session_analysis.true_wind`` — the per-timestamp true wind series
this session's own analysis settled on (see workers/process_upload/
processing/wind_estimation.py). Lets the session/activity map prefer it over
the ephemeral WindCard/live snapshot when present.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('session_analysis', sa.Column('true_wind', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('session_analysis', 'true_wind')
