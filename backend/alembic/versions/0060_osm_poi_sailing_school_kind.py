"""Allow ``osm_pois.kind = 'sailing_school'``.

``amenity=sailing_school`` (191 uses worldwide) is a place this app's users
want to find, and until now it classified as nothing at all unless the
element happened to carry a club or facility tag too. ``POI_KINDS`` in
``db/models/osm_poi.py`` gains the value and the CHECK constraint has to be
rewritten to match, or every row the refill classifies that way fails to
insert.

The rule sits directly below ``sailing_club`` and above ``marina`` in
``KIND_RULES`` — "who runs the place outranks what the place has", the same
principle that put the club rule where it is. A club that also teaches
(``amenity=sailing_school;boat_storage`` + ``club=sport``, which is exactly
how "Circolo Nautico di Volano" is tagged) pins as a club; a place that only
teaches pins as a school. Nothing is lost by that choice: since ``0059`` the
element's raw tags are stored next to the kind.

No cache-clearing statement here — ``0058`` (same release) already clears
every cell's ``fetched_at``, so the refill applies the new rule.

Revision ID: 0060
Revises: 0059
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0060'
down_revision: Union[str, None] = '0059'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = ("marina", "harbour", "slipway", "sailing_club", "sports_area",
        "fuel", "anchorage")
_NEW = ("marina", "harbour", "slipway", "sailing_club", "sailing_school",
        "sports_area", "fuel", "anchorage")


def _check(values: "tuple[str, ...]") -> str:
    return "kind IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint('kind_allowed', 'osm_pois', type_='check')
    op.create_check_constraint('kind_allowed', 'osm_pois', _check(_NEW))


def downgrade() -> None:
    """A downgrade has to cope with rows the narrower constraint would
    reject, and here it can do so honestly: ``osm_pois`` is a cache of
    OpenStreetMap, so a deleted row costs a re-fetch and nothing else.

    The schools are therefore dropped rather than coerced into some other
    kind (which would be a lie about what the element is) or left to make the
    constraint un-creatable. Their cells lose ``fetched_at`` with them, so the
    read path refills those places instead of serving a quietly thinned map
    for the next ``CELL_TTL_DAYS``.
    """
    # 0.25 is CELL_DEG / 2 as of this revision, spelled out rather than
    # imported: a migration has to describe the data it actually found.
    op.execute(
        """
        UPDATE osm_poi_cells AS c
           SET fetched_at = NULL
         WHERE c.fetched_at IS NOT NULL
           AND EXISTS (
                 SELECT 1 FROM osm_pois AS p
                  WHERE p.kind = 'sailing_school'
                    AND p.lat >= c.cell_lat - 0.25
                    AND p.lat <= c.cell_lat + 0.25
                    AND p.lng >= c.cell_lng - 0.25
                    AND p.lng <= c.cell_lng + 0.25
               )
        """
    )
    op.execute("DELETE FROM osm_pois WHERE kind = 'sailing_school'")
    op.drop_constraint('kind_allowed', 'osm_pois', type_='check')
    op.create_check_constraint('kind_allowed', 'osm_pois', _check(_OLD))
