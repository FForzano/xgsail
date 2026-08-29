"""Indexes for the personal-progression query: ``session_crew.user_id`` and
``sessions.started_at``.

``session_crew`` already has a unique constraint on
``(session_id, user_id)``, but a composite index leading with ``session_id``
doesn't serve a lookup keyed on ``user_id`` alone (e.g. "every session this
user crewed"). ``sessions.started_at`` is filtered/ordered by the same query
and had no index at all.

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0051'
down_revision: Union[str, None] = '0050'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_session_crew_user_id'), 'session_crew', ['user_id'], unique=False)
    op.create_index(op.f('ix_sessions_started_at'), 'sessions', ['started_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sessions_started_at'), table_name='sessions')
    op.drop_index(op.f('ix_session_crew_user_id'), table_name='session_crew')
