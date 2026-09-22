"""``clubs.has_sailing_school`` — does this club run a sailing school?

A fact about the club, declared by its own managers, and deliberately
independent of OpenStreetMap: plenty of clubs teach without being mapped as
``amenity=sailing_school``, and since ``0060`` a club that *is* so tagged
still classifies as ``sailing_club`` ("who runs the place outranks what the
place has"), so the school fact survives only inside ``osm_pois.tags``. OSM
can therefore *suggest* the flag (``GET /clubs/{id}/school-suggestion``) but
can never be the source of truth for it.

NOT NULL with a false default rather than a nullable "unknown" tri-state: the
column drives a badge and a filter, where "we don't know" and "no" render the
same way, so a third state would cost every consumer a NULL branch and buy
nothing. The genuinely unknown case is answered by the suggestion endpoint,
which is computed per request and never stored.

The server default is added and then dropped, the ``boats.is_guest`` pattern
from ``0052``: it exists only to backfill the existing rows in one statement,
after which the value comes from the ORM like every other column — which is
also what keeps ``alembic check`` quiet against a model carrying a plain
``default=False``.

Revision ID: 0061
Revises: 0060
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0061'
down_revision: Union[str, None] = '0060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'clubs',
        sa.Column('has_sailing_school', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )
    op.alter_column('clubs', 'has_sailing_school', server_default=None)


def downgrade() -> None:
    op.drop_column('clubs', 'has_sailing_school')
