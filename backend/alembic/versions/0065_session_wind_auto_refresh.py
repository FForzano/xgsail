"""``sessions`` wind auto-refresh bookkeeping.

A session analysed before another boat sailing the same water uploads never
sees that boat's tack/gybe wind observations. ``services/wind_auto_refresh.py``
marks such neighbours stale when a session's observation set materially
changes and a debounced, rate-limited processor re-runs their wind refresh.

- ``wind_stale_at``: last neighbour mark (re-stamped on each new mark).
- ``wind_auto_refreshed_at``: last automatic attempt — the cooldown.
- ``wind_auto_refresh_pending_at``: set just before an automatic dispatch,
  consumed by that analysis's upsert, so an auto-refreshed analysis never
  marks further sessions (one generation only).

All nullable, NULL being the normal state, and no backfill: existing sessions
are simply not stale until a neighbour's analysis changes.

Revision ID: 0065
Revises: 0064
Create Date: 2026-09-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0065'
down_revision: Union[str, None] = '0064'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ('wind_stale_at', 'wind_auto_refreshed_at', 'wind_auto_refresh_pending_at')


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column('sessions', sa.Column(name, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column('sessions', name)
