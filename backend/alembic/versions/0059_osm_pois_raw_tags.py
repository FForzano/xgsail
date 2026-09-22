"""``osm_pois.tags`` — keep the OSM tag dict the classification was derived
from, instead of only its verdict.

``parse_elements`` already received every element's full tags from Overpass
(``out center tags`` asks for them) and threw them away, persisting only the
classified ``kind``. That is the direct cause of the two cache-clearing
migrations in this table's short history: ``0056`` (``sailing_club`` moved
above ``marina``) and ``0058`` (tag values are ``;``-separated lists) could
not reclassify anything, because nothing on disk said *why* a row was a
marina. Their only available remedy was to throw the cache away and make
every deployment re-fetch it from a volunteer-run service, waiting up to
``CELL_TTL_DAYS`` for the map to agree with itself again. With the tags
stored, the next rule change is an ``UPDATE``.

Nullable, and **deliberately not backfilled**: a migration must not read
object storage or call Overpass, and there is no local source for a tag dict
that was discarded. It needs no backfill either, because ``0058`` — unshipped
and in this same release — already clears ``fetched_at`` on every cell, so
the full refill that is about to happen anyway populates ``tags`` for free.
Until a given cell refills, its rows keep ``tags = NULL``; nothing reads the
column yet and nothing may assume it is set.

``sa.JSON`` rather than ``JSONB``: the pytest suite runs on in-memory SQLite,
and this column is written and read whole, never queried by key.

Revision ID: 0059
Revises: 0058
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0059'
down_revision: Union[str, None] = '0058'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('osm_pois', sa.Column('tags', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drops the tags again. Lossy but harmless: this is a cache, the column
    holds nothing that was not fetched from Overpass, and re-upgrading simply
    leaves it NULL until each cell's next refill."""
    op.drop_column('osm_pois', 'tags')
