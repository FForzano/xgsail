"""Server-side cache of the nautical points of interest the explorer map
draws from OpenStreetMap (marinas, harbours, slipways, sailing clubs,
anchorages).

Two tables, because "what we know" and "where we have looked" are different
questions:

- ``osm_pois``: the elements themselves, keyed by ``osm_ref``
  (``"{osm_type}/{osm_id}"`` — deliberately the same format as
  ``clubs.osm_ref``, so a club and a POI can be compared with an equality
  check rather than a parser).
- ``osm_poi_cells``: the coverage register — one row per grid cell we have
  ever asked Overpass about (see ``services/osm_poi.py`` for the cell size).
  Without it an empty stretch of coast is indistinguishable from one nobody
  has fetched yet.

``osm_poi_cells`` carries **two** timestamps, and the distinction is the
whole staleness policy:

- ``fetched_at`` — last *successful* refresh. It alone decides whether a
  cell's data is stale (``CELL_TTL_DAYS``), and whether the cell is covered
  at all (NULL = never successfully fetched).
- ``attempted_at`` — last attempt, successful or not. It exists so a
  down or rate-limiting Overpass is asked again at most every
  ``RETRY_AFTER_FAILURE_MIN``, instead of once per user request. Overpass is
  a volunteer-run service with no SLA and it does go down; hammering it
  while it is down is both useless and rude.

Sizing, since the deployment target is a small private server: worldwide
there are ~137k elements across every tag we query (leisure=marina 31.8k,
leisure=slipway 68.1k, seamark:type=harbour 25.0k, harbour=yes 5.1k,
seamark:type=anchorage 4.6k, sport=sailing 1.7k, club=sailing 0.55k). At
~130 bytes a row that is ~18 MB for the entire planet — and only cells
someone actually looked at are ever stored, so the real figure is a small
fraction of that. The cache is bounded by construction; no eviction job.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDPKMixin, enum_check

# Mirrors ``PoiKind`` in frontend/src/services/overpass.ts; the classification
# that produces them lives in services/osm_poi.py.
POI_KINDS = ("marina", "harbour", "slipway", "sailing_club", "sports_area",
             "fuel", "anchorage")


class OsmPoiORM(TimestampMixin, UUIDPKMixin, Base):
    __tablename__ = "osm_pois"
    __table_args__ = (
        # One row per OSM element: what makes a cell refresh an idempotent
        # upsert rather than an append.
        UniqueConstraint("osm_ref"),
        enum_check("kind", POI_KINDS),
        # Every read is a bbox window (see repositories/sql/osm_poi_repo.py).
        Index("ix_osm_pois_lat_lng", "lat", "lng"),
    )

    # ``id`` is an internal surrogate; the client identifies a POI by its
    # ``osm_ref`` (and so does clubs.osm_ref), so the wire payload is exactly
    # the five fields the map needs.
    __wire_exclude__ = ("id", "created_at", "updated_at")

    osm_ref: Mapped[str] = mapped_column(String, nullable=False)  # "way/123456"
    kind: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class OsmPoiCellORM(UUIDPKMixin, Base):
    """One grid cell we have asked Overpass about — see the module docstring
    for why ``fetched_at`` and ``attempted_at`` are both here."""

    __tablename__ = "osm_poi_cells"
    __table_args__ = (
        # The cell key (its center, quantised by ``services/osm_poi.cell_of``).
        UniqueConstraint("cell_lat", "cell_lng"),
    )

    cell_lat: Mapped[float] = mapped_column(Float, nullable=False)
    cell_lng: Mapped[float] = mapped_column(Float, nullable=False)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
