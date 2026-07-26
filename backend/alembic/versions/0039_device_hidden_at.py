"""Hide (forget) revoked devices from device lists.

Adds ``devices.hidden_at``. A revoked device's row must stay (ingest records
RESTRICT-reference ``devices.id``), so "unlink and stop seeing it" is a soft
hide rather than a delete: set once, on an already-revoked device, and
``list()`` excludes hidden rows from then on.

Revision ID: 0039
Revises: 0038
Create Date: 2026-07-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0039'
down_revision: Union[str, None] = '0038'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('devices', sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('devices', 'hidden_at')
