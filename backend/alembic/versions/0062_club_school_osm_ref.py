"""``clubs.school_osm_ref`` — *which* OSM element is this club's school.

``0061`` added ``has_sailing_school``, which says that a club teaches but not
what element the school is. That is not enough to stop the explorer map
drawing two pins for one place: where the school is a **separate** OSM
element from the club (``amenity=sailing_school`` a few hundred metres away,
the "nearby" tier of ``GET /clubs/{id}/school-suggestion``), confirming the
suggestion recorded nothing the map could dedupe against, so the school kept
its own pin next to the club's. This column records the confirmed element, in
the same ``"{osm_type}/{osm_id}"`` form as ``osm_ref``, so the frontend
compares it to ``NauticalPoi.id`` with no parsing on either side.

UNIQUE, exactly like ``osm_ref`` and for the same reason: one OSM element
belongs to at most one club, and that constraint *is* the anti-duplication
guarantee. Nullable with no backfill — NULL is the normal state, and also the
right one for the "linked" tier, where the school is tagged on the club's own
element and ``osm_ref`` already dedupes the single pin.

Revision ID: 0062
Revises: 0061
Create Date: 2026-09-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0062'
down_revision: Union[str, None] = '0061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clubs', sa.Column('school_osm_ref', sa.String(), nullable=True))
    op.create_unique_constraint(op.f('uq_clubs_school_osm_ref'), 'clubs',
                                ['school_osm_ref'])


def downgrade() -> None:
    op.drop_constraint(op.f('uq_clubs_school_osm_ref'), 'clubs', type_='unique')
    op.drop_column('clubs', 'school_osm_ref')
