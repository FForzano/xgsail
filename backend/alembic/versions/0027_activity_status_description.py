"""Add ``status`` and ``description`` to activities.

``status`` distinguishes an already-happened activity (``completed``, the
default — matches every existing row, and every activity auto-created by
ingestion once a session lands) from one that's just an announcement of a
future club/group event with no session attached yet (``planned``). See
``routers/sessions.py::attach_to_activity`` for how a ``planned`` activity
flips to ``completed`` once a recording is attached to it.

``description`` is free-form event detail text (only relevant for
``planned`` announcements today, but not restricted to them).

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0027'
down_revision: Union[str, None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'activities',
        sa.Column('status', sa.String(), nullable=False, server_default='completed'),
    )
    op.create_check_constraint(
        op.f('ck_activities_status_allowed'), 'activities', "status IN ('planned', 'completed')",
    )
    op.add_column('activities', sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('activities', 'description')
    op.drop_constraint(op.f('ck_activities_status_allowed'), 'activities', type_='check')
    op.drop_column('activities', 'status')
