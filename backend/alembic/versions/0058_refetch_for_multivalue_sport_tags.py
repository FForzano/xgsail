"""Re-fetch every cached cell, after the Overpass query and ``KIND_RULES``
learned that OSM tag values are ``;``-separated lists.

``sport=sailing;kitesurfing;sup`` never matched ``sport == "sailing"``, and —
the part that matters here — never matched the ``["sport"="sailing"]``
selector either, so those elements were not merely misclassified: they were
never fetched at all. The widened query also now asks for
``leisure=sailing_club``. See ``services/osm_poi.py``.

Unlike ``0056``, this cannot be scoped. That revision only reordered rules
that could change a ``marina``/``slipway`` into a club, so a cell holding
neither was provably unaffected. Here the *query* widens: an element that was
never returned can now appear in any cell, including one that currently holds
no POIs at all (a cell whose only sailing club is tagged with a multi-value
``sport`` reads today as empty water). So every successfully fetched cell is
put back in the read path's cold-fill queue.

``attempted_at`` is left alone — it is what spaces the re-fetches out — and
the existing ``osm_pois`` rows stay in place, so each cell keeps drawing its
old pins until the refill replaces them.

Idempotent and data-only.

Revision ID: 0058
Revises: 0057
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0058'
down_revision: Union[str, None] = '0057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE osm_poi_cells
           SET fetched_at = NULL
         WHERE fetched_at IS NOT NULL
        """
    )


def downgrade() -> None:
    """Nothing to restore: the cleared timestamps described a fetch made with
    a query that could not see multi-value ``sport`` tags, and a cell without
    ``fetched_at`` is one the read path will fill again."""
