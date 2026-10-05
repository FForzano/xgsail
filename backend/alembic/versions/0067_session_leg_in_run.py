"""``session_legs.in_run``.

A leg classified "reach" that was sailed as part of a downwind run (gybes on
both sides), as flagged by the upload worker's straight-line segmentation.

NOT NULL with a ``false`` server default, so existing legs (analysed before the
flag existed) read as "not in a run" until their session is reanalysed.

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0067'
down_revision: Union[str, None] = '0066'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'session_legs',
        sa.Column('in_run', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('session_legs', 'in_run')
