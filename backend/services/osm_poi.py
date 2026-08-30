"""Nautical points of interest from OpenStreetMap, fetched from the public
Overpass API and cached in ``osm_pois``/``osm_poi_cells``.

Ported from the frontend (``frontend/src/services/overpass.ts``), which used
to query Overpass straight from the browser: load then scaled with users x
sessions x pans against a volunteer-run service with no SLA, and when it was
down the layer rendered nothing because nothing was kept. Server-side, the
same map costs Overpass one query per *place* — a 0.5 deg cell, refreshed at
most every ``CELL_TTL_DAYS`` — and keeps working while Overpass is out.

The query builder and ``KIND_RULES`` are a deliberate mirror of that
frontend module: same tag clauses, same first-match-wins ordering, same rule
dropping an unnamed generic sailing area. Fetch and parse are split (as in
``services/wind_providers/``) so the classification is unit-testable with no
network.

Storage sizing is in ``db/models/osm_poi.py``; the staleness policy lives in
the ``cell_needs_*`` predicates at the bottom of this module, which are pure
functions over a cell row so the three cases that matter (never fetched /
expired / recently failed) can be tested without a database.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Tried in order. The main instance does go down outright (not just 429), and
# with a single endpoint that means no data at all until the next retry
# window. Kept short on purpose: fanning out over many mirrors on every
# failure is exactly the load that gets a client blocked.
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
# Overpass's own server-side budget, and our socket timeout with slack on top.
QUERY_TIMEOUT_S = 60
FETCH_TIMEOUT_S = 90

# ~55 km of latitude. One Overpass query costs about the same whether it
# covers a marina or a whole gulf (the work is the index lookup, not the few
# hundred elements returned), so a coarse cell means far fewer queries for
# the same coverage — and a viewport at the zoom the layer turns on
# (NEAR_DETAIL_MIN_ZOOM = 11) is a small fraction of one cell, so a user
# panning around a coastline keeps hitting cells already fetched.
CELL_DEG = 0.5

# Marinas, harbours and slipways do not move, and their OSM tagging changes on
# the scale of months. Two months keeps the data honest while costing one
# query per visited cell per two months.
CELL_TTL_DAYS = 60

# After a failed attempt (or a successful one — see ``attempted_at``), don't
# ask again for an hour. Overpass failures are usually rate limiting or an
# outage lasting minutes to hours; retrying per user request would turn one
# outage into a flood.
RETRY_AFTER_FAILURE_MIN = 60

# How many never-fetched cells a single GET may fill inline. Each is one
# Overpass round trip, so this is the bound on how long a first visit to a
# new coastline can block. Four cells is ~110 km of coast either way.
MAX_COLD_CELLS_PER_REQUEST = 4

# How many cells one scheduler run refreshes. Bounds the run's duration and
# spreads the load: with cells expiring gradually, five per run is far more
# throughput than the expiry rate of any realistic instance.
MAX_CELLS_PER_REFRESH = 5

# Never burst at Overpass. Its usage policy asks for moderate, spaced
# queries; five seconds between calls keeps one refresh run well inside it.
PAUSE_BETWEEN_QUERIES_S = 5

# A viewport at the zoom this layer turns on is well under a degree across.
# This is not a tuning knob, it is the guard against a request that would
# sweep the planet — 5 deg is already 100 cells.
MAX_BBOX_SPAN_DEG = 5.0

POI_KINDS = ("marina", "harbour", "slipway", "sailing_club", "sports_area",
             "fuel", "anchorage")

# Ordered most- to least-specific: an element tagged both `leisure=marina`
# and `harbour=yes` should read as a marina, so the first match wins. The
# order is load-bearing — keep it in step with KIND_RULES in
# frontend/src/services/overpass.ts.
KIND_RULES = (
    ("marina", lambda t: t.get("leisure") == "marina"),
    ("slipway", lambda t: t.get("leisure") == "slipway"),
    ("sailing_club", lambda t: t.get("club") == "sailing"
        or (t.get("sport") == "sailing" and bool(t.get("club")))),
    ("anchorage", lambda t: t.get("seamark:type") == "anchorage"),
    ("fuel", lambda t: t.get("amenity") == "fuel" and bool(t.get("seamark:type"))),
    ("harbour", lambda t: t.get("seamark:type") == "harbour" or t.get("harbour") == "yes"),
    ("sports_area", lambda t: t.get("sport") == "sailing"),
)


# --- grid ------------------------------------------------------------------

def cell_of(lat: float, lng: float) -> "tuple[float, float]":
    """Quantize a coordinate to its cell center — same idiom as
    ``services/wind_estimates.grid_cell``, so a cell key is a pair of floats
    that compares exactly. The cell spans center +/- CELL_DEG / 2."""
    return (round(round(lat / CELL_DEG) * CELL_DEG, 6),
            round(round(lng / CELL_DEG) * CELL_DEG, 6))


def cell_bounds(cell_lat: float, cell_lng: float) -> "tuple[float, float, float, float]":
    """(south, west, north, east) of a cell — the bbox we query Overpass for."""
    half = CELL_DEG / 2
    return (round(cell_lat - half, 6), round(cell_lng - half, 6),
            round(cell_lat + half, 6), round(cell_lng + half, 6))


def cells_for_bbox(south: float, west: float, north: float,
                   east: float) -> "list[tuple[float, float]]":
    """Every cell whose square overlaps the bbox. Iterating cell *indices*
    (rather than stepping a float by CELL_DEG) keeps the keys identical to
    what ``cell_of`` produces for any point inside them."""
    lat0, lng0 = round(south / CELL_DEG), round(west / CELL_DEG)
    lat1, lng1 = round(north / CELL_DEG), round(east / CELL_DEG)
    return [
        (round(i * CELL_DEG, 6), round(j * CELL_DEG, 6))
        for i in range(lat0, lat1 + 1)
        for j in range(lng0, lng1 + 1)
    ]


def parse_bbox(raw: str) -> "tuple[float, float, float, float]":
    """Parse ``"<south>,<west>,<north>,<east>"``. Raises ``ValueError`` with a
    message the router turns into a 422."""
    parts = raw.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must be south,west,north,east")
    try:
        south, west, north, east = (float(p) for p in parts)
    except ValueError:
        raise ValueError("bbox coordinates must be numbers") from None
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise ValueError("latitude out of range")
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise ValueError("longitude out of range")
    if south >= north or west >= east:
        raise ValueError("bbox must be south < north and west < east")
    if north - south > MAX_BBOX_SPAN_DEG or east - west > MAX_BBOX_SPAN_DEG:
        raise ValueError(f"bbox may not span more than {MAX_BBOX_SPAN_DEG} degrees")
    return south, west, north, east


# --- Overpass query / parse ------------------------------------------------

def build_query(south: float, west: float, north: float, east: float) -> str:
    """`nwr` covers nodes, ways and relations in one clause; `out center tags`
    collapses ways/relations to a single representative point, which is all a
    map pin needs."""
    bbox = f"{south},{west},{north},{east}"
    clauses = "".join(
        f"nwr{selector}({bbox});"
        for selector in (
            '["leisure"="marina"]',
            '["leisure"="slipway"]',
            '["club"="sailing"]',
            '["sport"="sailing"]',
            '["seamark:type"="harbour"]',
            '["seamark:type"="anchorage"]',
            '["harbour"="yes"]',
            '["amenity"="fuel"]["seamark:type"]',
        )
    )
    return f"[out:json][timeout:{QUERY_TIMEOUT_S}];({clauses});out center tags;"


def classify(tags: dict) -> Optional[str]:
    for kind, matches in KIND_RULES:
        if matches(tags):
            return kind
    return None


def parse_elements(payload: dict) -> "list[dict]":
    """Overpass JSON -> the rows ``osm_pois`` stores. Elements with no
    position or no matching tag are dropped."""
    rows = []
    for el in payload.get("elements") or []:
        center = el.get("center") or {}
        lat = el.get("lat", center.get("lat"))
        lng = el.get("lon", center.get("lon"))
        if lat is None or lng is None:
            continue
        tags = el.get("tags") or {}
        kind = classify(tags)
        if kind is None:
            continue
        name = tags.get("name")
        # An unnamed marina/harbour is still worth a pin; an unnamed generic
        # "sailing area" polygon is just noise on the map.
        if not name and kind in ("sports_area", "sailing_club"):
            continue
        osm_type, osm_id = el.get("type"), el.get("id")
        if not osm_type or osm_id is None:
            continue
        rows.append({"osm_ref": f"{osm_type}/{osm_id}", "kind": kind,
                     "lat": float(lat), "lng": float(lng), "name": name})
    return rows


def query_overpass(south: float, west: float, north: float, east: float) -> dict:
    """POST the query to each endpoint in turn, returning the first answer.
    Raises if every endpoint fails."""
    body = {"data": build_query(south, west, north, east)}
    last_error: Optional[Exception] = None
    for endpoint in ENDPOINTS:
        try:
            resp = requests.post(endpoint, data=body, timeout=FETCH_TIMEOUT_S)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.info("overpass endpoint %s failed: %r", endpoint, exc)
            last_error = exc
    raise last_error or RuntimeError("Overpass unreachable")


def fetch_cell(cell_lat: float, cell_lng: float) -> "list[dict]":
    """Every POI in one cell, straight from Overpass. No caching here — the
    caller owns the cache bookkeeping."""
    return parse_elements(query_overpass(*cell_bounds(cell_lat, cell_lng)))


# --- staleness policy ------------------------------------------------------
#
# A cell row may be absent entirely (never asked), present with
# ``fetched_at IS NULL`` (asked, never succeeded), or present with a
# ``fetched_at`` that is fresh or expired. These predicates are the single
# place those cases are decided; both call paths (the GET and the scheduler
# refresh) go through them.

def _stale(at: Optional[datetime], age: timedelta, now: datetime) -> bool:
    return at is None or at < now - age


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


def is_covered(cell) -> bool:
    """Has this cell ever been fetched successfully? Only ``fetched_at``
    answers that — an attempt that failed tells us nothing about the place."""
    return cell is not None and cell.fetched_at is not None


def may_attempt(cell, now: Optional[datetime] = None) -> bool:
    """Are we allowed to hit Overpass for this cell right now? False while
    the last attempt (success or failure) is inside the retry window."""
    if cell is None:
        return True
    return _stale(cell.attempted_at, timedelta(minutes=RETRY_AFTER_FAILURE_MIN), _now(now))


def needs_cold_fill(cell, now: Optional[datetime] = None) -> bool:
    """A cell the GET path should fill synchronously: never successfully
    fetched, and not attempted within the retry window.

    Note what is *not* here: a merely expired cell is never refreshed on the
    read path. Serving slightly old marinas instantly beats making a user
    wait on Overpass, and the scheduler below is what keeps them fresh. The
    only thing worth blocking a request for is having nothing at all."""
    return not is_covered(cell) and may_attempt(cell, now)


def needs_refresh(cell, now: Optional[datetime] = None) -> bool:
    """A cell due for re-fetching: successfully fetched once, older than the
    TTL, and outside the retry window. A never-fetched cell is deliberately
    not a refresh candidate — it is filled inline by the next GET that looks
    at it, so we only ever spend an Overpass query on somewhere real."""
    if not is_covered(cell):
        return False
    return (_stale(cell.fetched_at, timedelta(days=CELL_TTL_DAYS), _now(now))
            and may_attempt(cell, now))


# --- cache orchestration ---------------------------------------------------

def _fill_cell(repos, cell_lat: float, cell_lng: float) -> bool:
    """Fetch one cell from Overpass and store it. Returns whether it worked.

    The attempt is recorded *before* the request, so two requests arriving on
    the same never-seen cell at once don't both query Overpass, and an
    endpoint that hangs still closes the retry window.
    """
    now = datetime.now(timezone.utc)
    repos.osm_pois.mark_cell(cell_lat, cell_lng, attempted_at=now)
    try:
        rows = fetch_cell(cell_lat, cell_lng)
    except Exception:
        logger.warning("overpass fetch failed for cell %s,%s", cell_lat, cell_lng,
                       exc_info=True)
        return False
    repos.osm_pois.replace_cell_pois(cell_bounds(cell_lat, cell_lng), rows)
    repos.osm_pois.mark_cell(cell_lat, cell_lng,
                             attempted_at=now, fetched_at=datetime.now(timezone.utc))
    return True


def pois_in_bbox(repos, south: float, west: float, north: float, east: float) -> dict:
    """The cached POIs inside a bbox, filling never-fetched cells inline.

    ``coverage`` is ``"partial"`` whenever a cell overlapping the bbox still
    has no successful fetch — the frontend needs to tell "there is nothing
    here" from "we could not find out". Merely *expired* cells are served as
    they are: making a user wait on Overpass for data we already have would
    be a bad trade, so refreshing them happens after the response
    (``refresh_stale_cell_in``).
    """
    keys = cells_for_bbox(south, west, north, east)
    cells = repos.osm_pois.get_cells(keys)
    budget = MAX_COLD_CELLS_PER_REQUEST
    for key in keys:
        if budget <= 0:
            break
        if not needs_cold_fill(cells.get(key)):
            continue
        budget -= 1
        if _fill_cell(repos, *key):
            cells[key] = repos.osm_pois.get_cell(*key)

    complete = all(is_covered(cells.get(key)) for key in keys)
    pois = [p.to_dict() for p in repos.osm_pois.list_in_bbox(south, west, north, east)]
    return {"pois": pois, "coverage": "complete" if complete else "partial"}


def refresh_stale_cell_in(repos, keys: "list[tuple[float, float]]") -> bool:
    """Re-fetch **one** expired cell among ``keys``, if any is due. Returns
    whether a fetch was attempted.

    This is what keeps the cache from serving old data forever, and it is
    driven by the read path (as a background task, after the response) rather
    than by a scheduler on a timer. Two reasons that is the better trade here:
    the only cells whose staleness anyone can observe are the ones someone is
    looking at, and a request-driven refresh needs no extra process to exist
    and stay alive on a small self-hosted box.

    One cell, not a batch, so no pacing sleep is needed: a single Overpass
    query per request is already spaced by however often people look at maps,
    and ``may_attempt``'s retry window bounds it per cell regardless of how
    many requests arrive.
    """
    cells = repos.osm_pois.get_cells(keys)
    for key in keys:
        cell = cells.get(key)
        if cell is not None and needs_refresh(cell):
            _fill_cell(repos, *key)
            return True
    return False


def refresh_expired_cells(repos, sleep=None) -> dict:
    """Re-fetch the most stale cells in one batch — the ops lever behind
    ``POST /api/system/osm-poi/refresh``, for refreshing without waiting for
    someone to browse there. Routine freshness is handled by
    ``refresh_stale_cell_in`` on the read path. Oldest
    first, bounded by ``MAX_CELLS_PER_REFRESH``, spaced by
    ``PAUSE_BETWEEN_QUERIES_S`` so a run never bursts at Overpass."""
    now = datetime.now(timezone.utc)
    candidates = repos.osm_pois.list_expired_cells(
        before=now - timedelta(days=CELL_TTL_DAYS), limit=MAX_CELLS_PER_REFRESH,
    )
    sleep = sleep if sleep is not None else time.sleep
    refreshed = failed = skipped = 0
    queried = 0
    for cell in candidates:
        # A cell attempted moments ago is skipped rather than retried: with
        # oldest-first ordering, a failing Overpass would otherwise have every
        # run hammer the same five cells.
        if not may_attempt(cell, now):
            skipped += 1
            continue
        if queried:
            sleep(PAUSE_BETWEEN_QUERIES_S)
        queried += 1
        if _fill_cell(repos, cell.cell_lat, cell.cell_lng):
            refreshed += 1
        else:
            failed += 1
    return {"refreshed": refreshed, "failed": failed, "skipped": skipped}
