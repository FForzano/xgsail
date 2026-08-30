"""``osm_pois`` + ``osm_poi_cells`` — server-side cache of the OpenStreetMap
nautical POIs the explorer map draws.

The browser used to query the public Overpass API directly on every pan, so
load scaled with users x sessions x pans against a volunteer-run service with
no SLA — and when it was down the layer rendered nothing at all, because
nothing was kept. Moving the fetch server-side turns that into one query per
*place* (a 0.5 deg cell), and keeps the answer so the map still works while
Overpass is unavailable.

``osm_poi_cells`` is the coverage register: without it an empty stretch of
coast is indistinguishable from one nobody has looked at yet. It carries two
timestamps on purpose — ``fetched_at`` (last success) drives staleness,
``attempted_at`` (last attempt, success or not) stops us re-asking a failing
upstream on every request. See ``db/models/osm_poi.py`` and
``services/osm_poi.py``.

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0054'
down_revision: Union[str, None] = '0053'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'osm_pois',
        sa.Column('id', sa.Uuid(as_uuid=True), server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('osm_ref', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lng', sa.Float(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "kind IN ('marina', 'harbour', 'slipway', 'sailing_club', "
            "'sports_area', 'fuel', 'anchorage')",
            name=op.f('ck_osm_pois_kind_allowed'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_osm_pois')),
        sa.UniqueConstraint('osm_ref', name=op.f('uq_osm_pois_osm_ref')),
    )
    op.create_index('ix_osm_pois_lat_lng', 'osm_pois', ['lat', 'lng'])

    op.create_table(
        'osm_poi_cells',
        sa.Column('id', sa.Uuid(as_uuid=True), server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('cell_lat', sa.Float(), nullable=False),
        sa.Column('cell_lng', sa.Float(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_osm_poi_cells')),
        sa.UniqueConstraint('cell_lat', 'cell_lng',
                            name=op.f('uq_osm_poi_cells_cell_lat_cell_lng')),
    )


def downgrade() -> None:
    op.drop_table('osm_poi_cells')
    op.drop_index('ix_osm_pois_lat_lng', table_name='osm_pois')
    op.drop_table('osm_pois')
