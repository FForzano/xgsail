"""Nautical points of interest from OpenStreetMap (``/api/osm-poi``).

Pub-readable, like ``/api/wind/stations``: the data is public OSM content and
the explorer map draws it for logged-out visitors too. The browser used to
query Overpass directly; serving it from our own cache instead means one
query per place rather than per user per pan, and a map that still works
while Overpass is down (see ``services/osm_poi.py``).

Staleness is handled here rather than by a scheduler: after answering, one
expired cell the request touched is re-fetched in the background. The cells
whose age anyone can observe are exactly the ones being looked at, so the
read path is the honest trigger — and it needs no extra process to exist on
a small self-hosted box. ``POST /api/system/osm-poi/refresh`` stays as the
manual lever for refreshing without waiting for someone to browse there.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from ..services import osm_poi
from ._common import repos

router = APIRouter(prefix="/api/osm-poi", tags=["osm-poi"])


@router.get("")
def list_pois(background_tasks: BackgroundTasks,
              bbox: str = Query(..., description="south,west,north,east")):
    """POIs inside the bbox, plus whether we have actually looked everywhere
    in it yet (``coverage``: ``complete`` | ``partial``)."""
    try:
        south, west, north, east = osm_poi.parse_bbox(bbox)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    payload = osm_poi.pois_in_bbox(repos, south, west, north, east)
    # After the response, never during it — the caller gets cached rows now
    # and the cache gets one cell fresher for whoever comes next.
    background_tasks.add_task(
        osm_poi.refresh_stale_cell_in, repos,
        osm_poi.cells_for_bbox(south, west, north, east),
    )
    return payload
