"""SQL repository for the OpenStreetMap POI cache (``db/models/osm_poi.py``).

Data access only: which cells exist, which POIs fall in a bbox, and the one
non-trivial write — replacing a cell's contents with what Overpass just
returned. The staleness *policy* (fresh / expired / never fetched / recently
failed) lives in ``services/osm_poi.py``; this module only stores and reads
the two timestamps it decides on.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from ...db.models import OsmPoiCellORM, OsmPoiORM

_POI_FIELDS = ("kind", "lat", "lng", "name")


class SqlOsmPoiRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    # --- POIs ---

    def list_in_bbox(self, south: float, west: float, north: float,
                     east: float) -> "list[OsmPoiORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(OsmPoiORM).where(
                    OsmPoiORM.lat >= south, OsmPoiORM.lat <= north,
                    OsmPoiORM.lng >= west, OsmPoiORM.lng <= east,
                )
            ).all())

    def replace_cell_pois(self, bounds: "tuple[float, float, float, float]",
                          rows: "list[dict]") -> "tuple[int, int, int]":
        """Make the cell's stored POIs exactly what Overpass just returned:
        upsert by ``osm_ref``, then drop the rows inside the cell that are no
        longer there (a marina can be deleted or retagged in OSM). Returns
        (inserted, updated, deleted).

        Plain ORM rather than a dialect-specific bulk upsert: a cell holds
        tens to a few hundred rows, and this way the same code path is
        exercised by the tests. ``osm_ref`` is unique table-wide, so an
        element whose ``out center`` point sits just outside its own cell
        still round-trips through whichever cell contains that point.
        """
        south, west, north, east = bounds
        seen = {r["osm_ref"]: r for r in rows}
        inserted = updated = deleted = 0
        with self.Session() as s:
            in_cell = and_(OsmPoiORM.lat >= south, OsmPoiORM.lat <= north,
                           OsmPoiORM.lng >= west, OsmPoiORM.lng <= east)
            # Both halves matter: the rows in the cell (candidates for
            # deletion) and the rows Overpass returned (candidates for
            # update, wherever they currently sit).
            match = or_(in_cell, OsmPoiORM.osm_ref.in_(list(seen))) if seen else in_cell
            existing = {
                orm.osm_ref: orm
                for orm in s.scalars(select(OsmPoiORM).where(match)).all()
            }
            for osm_ref, row in seen.items():
                orm = existing.get(osm_ref)
                if orm is None:
                    s.add(OsmPoiORM(osm_ref=osm_ref,
                                    **{k: row.get(k) for k in _POI_FIELDS}))
                    inserted += 1
                    continue
                if any(getattr(orm, k) != row.get(k) for k in _POI_FIELDS):
                    for k in _POI_FIELDS:
                        setattr(orm, k, row.get(k))
                    updated += 1
            for osm_ref, orm in existing.items():
                if osm_ref not in seen and south <= orm.lat <= north and west <= orm.lng <= east:
                    s.delete(orm)
                    deleted += 1
            s.commit()
        return inserted, updated, deleted

    # --- coverage cells ---

    def get_cell(self, cell_lat: float, cell_lng: float) -> Optional[OsmPoiCellORM]:
        with self.Session() as s:
            return s.scalars(
                select(OsmPoiCellORM).where(OsmPoiCellORM.cell_lat == cell_lat,
                                            OsmPoiCellORM.cell_lng == cell_lng)
            ).first()

    def get_cells(self, keys: "list[tuple[float, float]]") -> "dict[tuple, OsmPoiCellORM]":
        """The cell rows for a bbox's keys, as {(cell_lat, cell_lng): row} —
        one query, since a GET asks about every cell it overlaps."""
        if not keys:
            return {}
        lats = {k[0] for k in keys}
        lngs = {k[1] for k in keys}
        wanted = set(keys)
        with self.Session() as s:
            rows = s.scalars(
                select(OsmPoiCellORM).where(OsmPoiCellORM.cell_lat.in_(lats),
                                            OsmPoiCellORM.cell_lng.in_(lngs))
            ).all()
        return {(r.cell_lat, r.cell_lng): r for r in rows
                if (r.cell_lat, r.cell_lng) in wanted}

    def list_expired_cells(self, before: datetime, limit: int) -> "list[OsmPoiCellORM]":
        """Successfully-fetched cells whose data predates ``before``, oldest
        first. Never-fetched cells are excluded — those belong to the read
        path (see ``services/osm_poi.needs_refresh``)."""
        with self.Session() as s:
            return list(s.scalars(
                select(OsmPoiCellORM)
                .where(OsmPoiCellORM.fetched_at.is_not(None),
                       OsmPoiCellORM.fetched_at < before)
                .order_by(OsmPoiCellORM.fetched_at.asc())
                .limit(limit)
            ).all())

    def mark_cell(self, cell_lat: float, cell_lng: float, *, attempted_at: datetime,
                  fetched_at: Optional[datetime] = None) -> OsmPoiCellORM:
        """Record an attempt on a cell, creating its row if this was the
        first. ``fetched_at`` is passed only on success, so a failure updates
        ``attempted_at`` alone and the cell stays uncovered."""
        for attempt in (1, 2):
            with self.Session() as s:
                orm = s.scalars(
                    select(OsmPoiCellORM).where(OsmPoiCellORM.cell_lat == cell_lat,
                                                OsmPoiCellORM.cell_lng == cell_lng)
                ).first()
                if orm is None:
                    orm = OsmPoiCellORM(cell_lat=cell_lat, cell_lng=cell_lng)
                    s.add(orm)
                orm.attempted_at = attempted_at
                if fetched_at is not None:
                    orm.fetched_at = fetched_at
                try:
                    s.commit()
                except IntegrityError:
                    # Two requests reached the same never-seen cell at once;
                    # the unique key made one of them lose. Re-read and update.
                    s.rollback()
                    if attempt == 2:
                        raise
                    continue
            break
        return self.get_cell(cell_lat, cell_lng)
