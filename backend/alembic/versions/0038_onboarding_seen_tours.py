"""Guided-tour progress on users.

Adds ``onboarding_seen_tours`` — a JSON-encoded array of tour IDs the user
has finished or skipped (see ``backend/onboarding.py`` and
``auth/permissions.py::_onboarding_status``). Tracked server-side, like the
"Buy Me a Coffee" reminder (``0034_support_prompt``), so a tour already seen
on one device doesn't repeat on another. One open-ended set rather than a
column per tour, so new tours can be added later with no further migration.

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0038'
down_revision: Union[str, None] = '0037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('onboarding_seen_tours', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'onboarding_seen_tours')
