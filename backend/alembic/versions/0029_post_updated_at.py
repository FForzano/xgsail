"""Add ``updated_at`` to posts, letting the author edit a post's body.

Stays NULL until the first edit, so it doubles as the "was this edited"
flag (see ``routers/posts.py::update_post``).

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0029'
down_revision: Union[str, None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('posts', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('posts', 'updated_at')
