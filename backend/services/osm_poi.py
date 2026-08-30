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
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

OVERPASS_USER_AGENT = os.getenv(
    "OVERPASS_USER_AGENT",
    "XGSail/1.0 (mailto:f.forzano@ieee.org)",
)

# Tried in order. The main instance does go down outright (not just 429), and
# with a single endpoint that means no data at all until the next retry
# window. Kept short on purpose: fanning out over many mirrors on every
# failure is exactly the load that gets a client blocked.
#
# Configured rather than hand-edited, because the list *is* the thing that
# gets fiddled with when Overpass misbehaves — and editing a tuple literal to
# do it is how the layer once ended up querying nothing at all: commenting out
# every entry but one left ``("https://...",)`` without its trailing comma,
# i.e. a plain string, and ``for endpoint in ENDPOINTS`` then iterated over
# its *characters*, POSTing to "h", to "t", to "t"... Each one raised, each
# was swallowed as a failed endpoint, and no request ever left the box while
# the logs said Overpass was unreachable. ``parse_endpoints`` is why that
# cannot happen again: a malformed setting is a startup error, not a silent
# reinterpretation.
DEFAULT_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)


def parse_endpoints(raw: Optional[str]) -> "tuple[str, ...]":
    """Comma- or whitespace-separated absolute URLs. Empty/unset means the
    defaults; anything present but unusable raises, since a mistyped endpoint
    list must not read as "Overpass is down"."""
    if raw is None or not raw.strip():
        return DEFAULT_ENDPOINTS
    endpoints = tuple(part.strip() for part in raw.replace(",", " ").split())
    bad = [e for e in endpoints if not e.startswith(("http://", "https://"))]
    if bad:
        raise ValueError(f"OVERPASS_ENDPOINTS must be absolute http(s) URLs; got {bad}")
    return endpoints


ENDPOINTS = parse_endpoints(os.getenv("OVERPASS_ENDPOINTS"))
# Overpass's own server-side budget, and our socket timeout with slack on top.
# Deliberately far below what Overpass would allow: a 0.5 deg cell with these
# selectors answers in a few seconds, and anything slower is a struggling
# instance we would rather give up on than make a user wait for. The read path
# runs behind nginx's default 60 s ``proxy_read_timeout``, so a request that
# outlives that is a 504 the browser reports as "the map is broken".
QUERY_TIMEOUT_S = 25
FETCH_TIMEOUT_S = 30

# Wall-clock ceiling on the Overpass work one request may do. The read path's
# is what keeps ``GET /osm-poi`` inside nginx's timeout no matter how many
# cold cells the viewport covers or how slow Overpass is; the background
# budget is looser because nobody is waiting on it.
READ_FILL_BUDGET_S = 25
BACKGROUND_FILL_BUDGET_S = 120

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
# Overpass round trip, and they run one after another, so this multiplies
# straight into the request's latency — two cells is ~55 km of coast either
# way, and the rest of the viewport comes back on the next pan once these are
# cached. ``READ_FILL_BUDGET_S`` is the real ceiling; this keeps a fast
# Overpass from being asked for more than a viewport actually needs.
MAX_COLD_CELLS_PER_REQUEST = 2

# How many cells one scheduler run refreshes. Bounds the run's duration and
# spreads the load: with cells expiring gradually, five per run is far more
# throughput than the expiry rate of any realistic instance.
MAX_CELLS_PER_REFRESH = 5

# Never burst at Overpass. Its usage policy asks for moderate, spaced
# queries; five seconds between calls keeps one refresh run well inside it.
PAUSE_BETWEEN_QUERIES_S = 5

# Every query now leaves from one server IP instead of from each visitor's
# browser, and overpass-api.de rations by IP (a couple of concurrent slots
# plus a rolling download quota). So the whole process takes turns: one query
# in flight at a time, and the read path never *waits* for that turn — a
# request that cannot have it serves what is cached and reports partial
# coverage, which is the honest answer and an instant one.
_query_gate = threading.Lock()

# How long a background fill will wait for its turn. The read path passes 0.
SLOT_WAIT_S = 30

# Circuit breaker. The per-cell retry window (``may_attempt``) does nothing
# for an outage, because every *new* cell is still a first attempt: a user
# panning across an unfetched coast would spend the full budget on every
# request while Overpass is down. Consecutive failures therefore park the
# whole layer for a cooldown, and a 429 parks it for longer straight away —
# continuing to knock is what turns throttling into a block.
BREAKER_FAILURES = 3
BREAKER_COOLDOWN_S = 300
RATE_LIMIT_COOLDOWN_S = 900
MAX_RETRY_AFTER_S = 3600

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

class OverpassError(RuntimeError):
    """Overpass did not return usable data. Carries the HTTP status when there
    was one, and ``retry_after`` when the answer said how long to wait."""

    def __init__(self, message: str, *, status: Optional[int] = None,
                 retry_after: Optional[float] = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after

    @property
    def rate_limited(self) -> bool:
        return self.status in (429, 504)


def build_query(south: float, west: float, north: float, east: float,
                timeout_s: int = QUERY_TIMEOUT_S) -> str:
    """`nwr` covers nodes, ways and relations in one clause; `out center tags`
    collapses ways/relations to a single representative point, which is all a
    map pin needs.

    ``timeout_s`` is Overpass's *own* budget for the query. It tracks the time
    we are actually prepared to wait: asking for more than that just has the
    server keep working on an answer nobody will read.
    """
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
    return f"[out:json][timeout:{timeout_s}];({clauses});out center tags;"


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


def check_payload(payload) -> dict:
    """Overpass reports a *runtime* error inside a **200 OK** body: valid JSON,
    an ``elements`` list that is empty or truncated, and a ``remark`` saying
    the query timed out or ran out of memory. Taking that at face value is the
    worst failure mode this module has — the caller would store zero POIs over
    a cell that has plenty, stamp it fetched, and serve an empty map there,
    reported as ``coverage: "complete"``, until the TTL expires two months
    later. So a remark that mentions an error is a failure, and a body with no
    ``elements`` key at all is not an Overpass answer we understand.
    """
    if not isinstance(payload, dict) or "elements" not in payload:
        raise OverpassError(f"unexpected Overpass payload: {str(payload)[:200]}")
    remark = payload.get("remark") or ""
    if "error" in remark.lower():
        raise OverpassError(f"Overpass runtime error: {remark[:300]}")
    return payload


def _retry_after_seconds(resp) -> Optional[float]:
    """``Retry-After`` in seconds, when the answer carried a sane one."""
    raw = resp.headers.get("Retry-After") if resp is not None else None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_S)


def query_overpass(south: float, west: float, north: float, east: float,
                   deadline: "Optional[float]" = None) -> dict:
    """POST the query to each endpoint in turn, returning the first usable
    answer. Raises ``OverpassError`` if every endpoint fails.

    ``deadline`` is a ``time.monotonic()`` instant this call must not outlive:
    each attempt gets whatever is left, and the endpoints stop being tried
    once nothing is. Without it a slow Overpass plus the mirror fallback adds
    up to minutes, which on the read path is a gateway timeout.
    """
    last_error: Optional[OverpassError] = None
    for endpoint in ENDPOINTS:
        timeout = float(FETCH_TIMEOUT_S)
        if deadline is not None:
            timeout = min(timeout, deadline - time.monotonic())
            if timeout < 1:
                logger.warning(
                    "Out of time before trying Overpass endpoint %s for bbox %s,%s,%s,%s",
                    endpoint, south, west, north, east,
                )
                break
        body = {"data": build_query(south, west, north, east,
                                    timeout_s=max(1, int(timeout)))}
        logger.info(
            "Trying Overpass endpoint %s for bbox %s,%s,%s,%s (timeout=%.0fs)",
            endpoint, south, west, north, east, timeout,
        )
        try:
            resp = requests.post(endpoint, data=body, timeout=timeout,
                                 headers={"User-Agent": OVERPASS_USER_AGENT})
            if resp.status_code >= 400:
                raise OverpassError(
                    f"HTTP {resp.status_code}: {(resp.text[:300] if resp.text else '<empty>')}",
                    status=resp.status_code,
                    retry_after=_retry_after_seconds(resp),
                )
            try:
                payload = resp.json()
            except ValueError as exc:
                # An overloaded instance answers 200 with an HTML error page.
                raise OverpassError(
                    f"non-JSON body: {(resp.text[:300] if resp.text else '<empty>')}"
                ) from exc
            payload = check_payload(payload)
            logger.info("Overpass request succeeded via endpoint %s for bbox %s,%s,%s,%s "
                        "(%s elements)", endpoint, south, west, north, east,
                        len(payload.get("elements") or []))
            return payload
        except OverpassError as exc:
            logger.warning(
                "Overpass endpoint %s rejected bbox %s,%s,%s,%s: %s; trying next endpoint",
                endpoint, south, west, north, east, exc,
            )
            last_error = exc
        except requests.exceptions.Timeout as exc:
            logger.warning(
                "Overpass timeout for endpoint %s while fetching bbox %s,%s,%s,%s "
                "(timeout=%.0fs); trying next endpoint",
                endpoint, south, west, north, east, timeout,
            )
            # Deliberately not flagged rate-limited: our own socket timeout
            # only says this instance was slow, and one slow query should not
            # park the layer the way an upstream 429/504 does. It still counts
            # toward the consecutive-failure breaker.
            last_error = OverpassError(f"timeout after {timeout:.0f}s: {exc!r}")
        except Exception as exc:
            logger.warning(
                "Overpass request failed for endpoint %s bbox %s,%s,%s,%s: %r; "
                "trying next endpoint", endpoint, south, west, north, east, exc,
            )
            last_error = OverpassError(repr(exc))
    logger.error(
        "All Overpass endpoints failed for bbox %s,%s,%s,%s. Endpoints tried: %s. Last error: %s",
        south, west, north, east, ", ".join(ENDPOINTS), last_error,
    )
    raise last_error or OverpassError("Overpass unreachable")


def fetch_cell(cell_lat: float, cell_lng: float,
               deadline: "Optional[float]" = None) -> "list[dict]":
    """Every POI in one cell, straight from Overpass. No caching here — the
    caller owns the cache bookkeeping."""
    return parse_elements(query_overpass(*cell_bounds(cell_lat, cell_lng),
                                         deadline=deadline))


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


# --- rate-limit gate & circuit breaker -------------------------------------

_breaker_lock = threading.Lock()
_consecutive_failures = 0
_blocked_until = 0.0  # time.monotonic() instant


def reset_breaker() -> None:
    """Forget the failure history — used by tests and by the manual refresh
    lever, where a human asking for a retry outranks the cooldown."""
    global _consecutive_failures, _blocked_until
    with _breaker_lock:
        _consecutive_failures = 0
        _blocked_until = 0.0


def breaker_blocked_for() -> float:
    """Seconds left on the cooldown, 0 when Overpass may be called."""
    with _breaker_lock:
        return max(0.0, _blocked_until - time.monotonic())


def _record_success() -> None:
    global _consecutive_failures, _blocked_until
    with _breaker_lock:
        _consecutive_failures = 0
        _blocked_until = 0.0


def _record_failure(exc: BaseException) -> None:
    global _consecutive_failures, _blocked_until
    rate_limited = isinstance(exc, OverpassError) and exc.rate_limited
    retry_after = getattr(exc, "retry_after", None)
    with _breaker_lock:
        _consecutive_failures += 1
        if rate_limited:
            cooldown = retry_after or RATE_LIMIT_COOLDOWN_S
        elif _consecutive_failures >= BREAKER_FAILURES:
            cooldown = BREAKER_COOLDOWN_S
        else:
            return
        _blocked_until = max(_blocked_until, time.monotonic() + cooldown)
    logger.warning("Overpass paused for %.0fs after %s failure(s): %s",
                   cooldown, _consecutive_failures, exc)


def _acquire_slot(wait: bool) -> bool:
    """Take the process's single Overpass slot, or report that we shouldn't
    query at all right now. ``wait=False`` (the read path) never blocks: the
    caller serves what is cached instead."""
    blocked = breaker_blocked_for()
    if blocked:
        logger.info("Skipping Overpass: paused for another %.0fs", blocked)
        return False
    if wait:
        return _query_gate.acquire(timeout=SLOT_WAIT_S)
    return _query_gate.acquire(blocking=False)


# --- cache orchestration ---------------------------------------------------

def _fill_cell(repos, cell_lat: float, cell_lng: float, *,
               deadline: "Optional[float]" = None, wait: bool = False) -> bool:
    """Fetch one cell from Overpass and store it. Returns whether it worked.

    The attempt is recorded *before* the request, so two requests arriving on
    the same never-seen cell at once don't both query Overpass, and an
    endpoint that hangs still closes the retry window. Nothing is recorded
    when the gate or the breaker turned us away — that is not an attempt on
    the cell, and marking it would suppress the retry for an hour over a
    failure that had nothing to do with this place.
    """
    if not _acquire_slot(wait):
        return False
    try:
        now = datetime.now(timezone.utc)
        repos.osm_pois.mark_cell(cell_lat, cell_lng, attempted_at=now)
        try:
            rows = fetch_cell(cell_lat, cell_lng, deadline=deadline)
        except Exception as exc:
            _record_failure(exc)
            logger.warning("overpass fetch failed for cell %s,%s: %s",
                           cell_lat, cell_lng, exc)
            return False
        _record_success()
    finally:
        _query_gate.release()
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
    deadline = time.monotonic() + READ_FILL_BUDGET_S
    for key in keys:
        # The breaker is checked here too, not only inside the fill: a paused
        # layer would otherwise walk every cell in the bbox to be turned away
        # by each one.
        if budget <= 0 or time.monotonic() >= deadline or breaker_blocked_for():
            break
        if not needs_cold_fill(cells.get(key)):
            continue
        budget -= 1
        if _fill_cell(repos, *key, deadline=deadline):
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
            _fill_cell(repos, *key, wait=True,
                       deadline=time.monotonic() + BACKGROUND_FILL_BUDGET_S)
            return True
    return False


def refresh_expired_cells(repos, sleep=None) -> dict:
    """Re-fetch the most stale cells in one batch — the ops lever behind
    ``POST /api/system/osm-poi/refresh``, for refreshing without waiting for
    someone to browse there. Routine freshness is handled by
    ``refresh_stale_cell_in`` on the read path. Oldest
    first, bounded by ``MAX_CELLS_PER_REFRESH``, spaced by
    ``PAUSE_BETWEEN_QUERIES_S`` so a run never bursts at Overpass. Being the
    lever a human pulls, it clears the circuit breaker first — otherwise
    "refresh now" would silently do nothing during a cooldown."""
    reset_breaker()
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
        if _fill_cell(repos, cell.cell_lat, cell.cell_lng, wait=True,
                      deadline=time.monotonic() + BACKGROUND_FILL_BUDGET_S):
            refreshed += 1
        else:
            failed += 1
    return {"refreshed": refreshed, "failed": failed, "skipped": skipped}
