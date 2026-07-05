"""Membership pending states for the invite/discovery flows.

- Add ``user_groups.status`` (mirrors ``user_clubs``); existing rows = active.
- Add ``requested`` to both status enums: ``invited`` = manager invited the
  user (user self-accepts), ``requested`` = user asked to join (manager
  approves). With a single pending value the two flows would be
  indistinguishable and self-accept would bypass approval.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_groups',
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
    )
    op.create_check_constraint(
        'status_allowed', 'user_groups',
        "status IN ('invited', 'requested', 'active')",
    )
    op.drop_constraint('status_allowed', 'user_clubs', type_='check')
    op.create_check_constraint(
        'status_allowed', 'user_clubs',
        "status IN ('invited', 'requested', 'active', 'deleted')",
    )


def downgrade() -> None:
    op.drop_constraint('status_allowed', 'user_clubs', type_='check')
    op.create_check_constraint(
        'status_allowed', 'user_clubs',
        "status IN ('invited', 'active', 'deleted')",
    )
    op.drop_constraint('status_allowed', 'user_groups', type_='check')
    op.drop_column('user_groups', 'status')
