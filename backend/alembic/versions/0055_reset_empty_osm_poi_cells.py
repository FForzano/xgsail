"""Un-poison ``osm_poi_cells`` rows that a throttled Overpass filled with
nothing.

Overpass reports a *runtime* error (query timed out, out of memory — what a
rate-limited or overloaded instance returns) inside an **HTTP 200** body: valid
JSON, an empty ``elements`` list and a ``remark``. ``services/osm_poi.py`` used
to take that at face value, so every such answer deleted the cell's POIs and
stamped ``fetched_at``. The cell then read as fully covered, the map drew an
empty sea there with ``coverage: "complete"`` — no warning, since as far as the
cache was concerned there was simply nothing at that place — and it stayed that
way for the whole ``CELL_TTL_DAYS`` window.

The service now rejects those answers, but deploys are unattended and nothing
re-examines a cell before its TTL, so the databases that already applied the
damage would keep serving blank coastlines for two months. This clears
``fetched_at`` on every cell that holds no POIs at all, which puts it back in
the read path's cold-fill queue and gets it re-fetched the next time somebody
looks there.

Genuinely empty cells (open ocean) are re-fetched once and marked covered
again — one Overpass query for a handful of cells, against the certainty that
every wrongly-blanked one is repaired. ``attempted_at`` is deliberately left
alone: it is what spaces the retries out.

Data-only and idempotent, so it is a no-op on a database that never cached a
bad answer.

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-30
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0055'
down_revision: Union[str, None] = '0054'
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
           AND NOT EXISTS (
                 SELECT 1 FROM osm_pois AS p
                  WHERE p.lat >= c.cell_lat - 0.25
                    AND p.lat <= c.cell_lat + 0.25
                    AND p.lng >= c.cell_lng - 0.25
                    AND p.lng <= c.cell_lng + 0.25
               )
        """
    )


def downgrade() -> None:
    """Nothing to restore: the cleared timestamps recorded a fetch that had
    returned no usable data, and a cell with no ``fetched_at`` is simply one
    the read path will fill again."""
