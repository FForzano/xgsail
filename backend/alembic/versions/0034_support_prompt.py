"""Backend-tracked "Buy Me a Coffee" reminder state on users.

Adds ``support_prompt_next_at`` (earliest time the in-app support banner may
be shown again — NULL means "not yet shown, use the default 30-day-from-
registration threshold") and ``support_donated_at`` (set once the user
confirms they've supported the project, so the next reminder waits a full
year instead of a few weeks). Tracked server-side rather than in
localStorage so the reminder cadence is consistent across devices/reinstalls
(see SupportPromptBanner on the frontend).

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0034'
down_revision: Union[str, None] = '0033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('support_prompt_next_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('support_donated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'support_donated_at')
    op.drop_column('users', 'support_prompt_next_at')
