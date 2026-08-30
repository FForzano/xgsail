"""Link a club to the OpenStreetMap element it is (``clubs.osm_ref``).

The explorer map draws clubs from two independent sources — XGSail's own
``clubs`` rows and OSM POIs fetched live from Overpass — so the same real
club appeared twice. ``osm_ref`` stores ``"{osm_type}/{osm_id}"``, the exact
string the frontend already uses as the POI id, so the dedupe is an equality
check. UNIQUE: one OSM element maps to at most one club, which is what stops
two clubs both claiming the same POI.

Nullable with no backfill — every existing club stays unlinked until someone
creates one from a POI or claims one.

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0053'
down_revision: Union[str, None] = '0052'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clubs', sa.Column('osm_ref', sa.String(), nullable=True))
    op.create_unique_constraint(op.f('uq_clubs_osm_ref'), 'clubs', ['osm_ref'])


def downgrade() -> None:
    op.drop_constraint(op.f('uq_clubs_osm_ref'), 'clubs', type_='unique')
    op.drop_column('clubs', 'osm_ref')
