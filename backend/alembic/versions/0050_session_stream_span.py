"""``session_streams.first_t`` / ``last_t`` — the span each series covers.

Choosing between several GPS tracks of one session
(``services/nav_source.py``) could previously only compare row counts, so a
device that stopped twenty minutes early but sampled faster outranked one that
covered the whole outing. The worker callback already reports
``start_time``/``end_time`` per processed file (``routers/system.py::
ingest_complete``) and the GPX import path already knows the first/last point,
so both are recorded here and the ranking becomes coverage-aware without
reading a single blob.

Backfill is deliberately omitted: the values live inside the processed series
in object storage, which a migration must not read. Existing rows keep NULL,
which ``nav_source`` treats as "span unknown" and which makes it fall back to
exactly the previous ordering for those sessions.

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0050'
down_revision: Union[str, None] = '0049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('session_streams',
                  sa.Column('first_t', sa.DateTime(timezone=True), nullable=True))
    op.add_column('session_streams',
                  sa.Column('last_t', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('session_streams', 'last_t')
    op.drop_column('session_streams', 'first_t')
