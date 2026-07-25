"""Add crew notes to sessions: a free-text field for boat setup, waves,
wind perception, trim results, and what to try next time. Shared by and
editable by any crew member (not per-author), private to the crew/boat
managers by default — ``notes_shared`` opts it into the session's normal
visibility. See ``auth.session_notes_visible_to``.

Revision ID: 0036
Revises: 0035
Create Date: 2026-07-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0036'
down_revision: Union[str, None] = '0035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column(
        'sessions',
        sa.Column('notes_shared', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('sessions', 'notes_shared', server_default=None)


def downgrade() -> None:
    op.drop_column('sessions', 'notes_shared')
    op.drop_column('sessions', 'notes')
