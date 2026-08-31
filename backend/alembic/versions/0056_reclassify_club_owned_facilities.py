"""Re-fetch the cells whose POIs may now classify differently, after
``sailing_club`` was moved above ``marina``/``slipway`` in ``KIND_RULES``.

The app is for sailing sports, so a circolo velico that also has berths should
pin as a club rather than as a marina — see the reasoning on ``KIND_RULES`` in
``services/osm_poi.py``. The catch is that ``osm_pois`` stores the *classified
kind* and not the OSM tags it was derived from, so nothing here can tell which
existing ``marina`` rows carry ``club=sailing``. The new rules can only be
applied by asking Overpass again.

Left alone, that would happen on its own — but not for up to ``CELL_TTL_DAYS``
(60), and deploys are unattended, so the map would keep contradicting itself
for two months. Clearing ``fetched_at`` puts a cell back in the read path's
cold-fill queue, so it is re-fetched the next time somebody looks there.

Scoped to cells that actually hold a ``marina`` or ``slipway``: the club rule
only overtook those two, everything below it kept its relative order, so no
other cell can change. ``attempted_at`` is left alone — it is what spaces the
re-fetches out — and the existing POIs stay in place, so those cells keep
drawing their (old) pins until the refill replaces them.

Idempotent and data-only.

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0056'
down_revision: Union[str, None] = '0055'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0.25 is CELL_DEG / 2 as of this revision, spelled out rather than
    # imported: a migration has to describe the data it actually found.
    op.execute(
        """
        UPDATE osm_poi_cells AS c
           SET fetched_at = NULL
         WHERE c.fetched_at IS NOT NULL
           AND EXISTS (
                 SELECT 1 FROM osm_pois AS p
                  WHERE p.kind IN ('marina', 'slipway')
                    AND p.lat >= c.cell_lat - 0.25
                    AND p.lat <= c.cell_lat + 0.25
                    AND p.lng >= c.cell_lng - 0.25
                    AND p.lng <= c.cell_lng + 0.25
               )
        """
    )


def downgrade() -> None:
    """Nothing to restore: the cleared timestamps described a fetch classified
    under rules that no longer apply, and a cell without ``fetched_at`` is one
    the read path will fill again."""
