"""The server-side OpenStreetMap POI cache (``services/osm_poi.py``).

Three things are worth pinning down, and none of them needs Postgres:

- the Overpass response parser and its classification — ported from
  ``frontend/src/services/overpass.ts``, where the rule order is
  load-bearing (first match wins) and an unnamed generic sailing area is
  deliberately dropped;
- the grid: which cell a coordinate falls in, and which cells a bbox needs;
- the staleness policy — never fetched vs. expired vs. fresh vs. recently
  attempted. Those four cases *are* the design, and getting one of them
  subtly wrong either hammers Overpass or serves an empty map forever.

The repository half runs against an in-memory SQLite engine, following
``test_club_osm_ref.py``; ``backend/routers/`` cannot be imported here (its
storage layer wants AWS credentials).
"""

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import OsmPoiCellORM, OsmPoiORM
from backend.repositories.sql.osm_poi_repo import SqlOsmPoiRepo
from backend.services import osm_poi

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _cell(fetched_at=None, attempted_at=None):
    return SimpleNamespace(cell_lat=45.5, cell_lng=9.0,
                           fetched_at=fetched_at, attempted_at=attempted_at)


def _element(osm_id=1, osm_type="node", lat=45.0, lon=9.0, **tags):
    return {"type": osm_type, "id": osm_id, "lat": lat, "lon": lon, "tags": tags}


# --- parsing & classification ------------------------------------------------

@pytest.mark.parametrize("tags,expected", [
    ({"leisure": "marina"}, "marina"),
    ({"leisure": "slipway"}, "slipway"),
    ({"club": "sailing"}, "sailing_club"),
    ({"sport": "sailing", "club": "yes"}, "sailing_club"),
    ({"seamark:type": "anchorage"}, "anchorage"),
    ({"amenity": "fuel", "seamark:type": "fuel_station"}, "fuel"),
    ({"seamark:type": "harbour"}, "harbour"),
    ({"harbour": "yes"}, "harbour"),
    ({"sport": "sailing"}, "sports_area"),
])
def test_each_kind_is_recognised(tags, expected):
    assert osm_poi.classify(tags) == expected


@pytest.mark.parametrize("tags", [
    {}, {"amenity": "fuel"}, {"leisure": "park"}, {"harbour": "no"},
])
def test_unrelated_tags_classify_as_nothing(tags):
    assert osm_poi.classify(tags) is None


def test_first_matching_rule_wins():
    # A marina that is also tagged as a harbour reads as a marina, not a
    # harbour — the KIND_RULES order is the whole reason.
    assert osm_poi.classify({"leisure": "marina", "harbour": "yes"}) == "marina"
    assert osm_poi.classify({"leisure": "slipway", "seamark:type": "harbour"}) == "slipway"
    # ...and a sailing club that is also a generic sailing area is a club.
    assert osm_poi.classify({"club": "sailing", "sport": "sailing"}) == "sailing_club"


def test_parses_a_named_marina():
    rows = osm_poi.parse_elements({"elements": [
        _element(osm_id=42, osm_type="way", lat=44.1, lon=9.2,
                 leisure="marina", name="Porto Vecchio"),
    ]})
    assert rows == [{"osm_ref": "way/42", "kind": "marina", "lat": 44.1,
                     "lng": 9.2, "name": "Porto Vecchio"}]


def test_way_center_is_used_when_there_is_no_node_position():
    rows = osm_poi.parse_elements({"elements": [
        {"type": "relation", "id": 7, "center": {"lat": 1.5, "lon": 2.5},
         "tags": {"leisure": "marina"}},
    ]})
    assert rows[0]["osm_ref"] == "relation/7"
    assert (rows[0]["lat"], rows[0]["lng"]) == (1.5, 2.5)


def test_elements_without_a_position_or_a_matching_tag_are_dropped():
    rows = osm_poi.parse_elements({"elements": [
        {"type": "way", "id": 1, "tags": {"leisure": "marina"}},   # no position
        _element(osm_id=2, leisure="park"),                        # no kind
        {"type": "node", "id": 3, "lat": 1.0, "lon": 1.0},         # no tags
    ]})
    assert rows == []


def test_an_unnamed_marina_is_kept_but_an_unnamed_sailing_area_is_not():
    rows = osm_poi.parse_elements({"elements": [
        _element(osm_id=1, leisure="marina"),
        _element(osm_id=2, sport="sailing"),
        _element(osm_id=3, club="sailing"),
        _element(osm_id=4, sport="sailing", name="Specchio acqueo regate"),
    ]})
    assert [r["osm_ref"] for r in rows] == ["node/1", "node/4"]


def test_an_empty_response_parses_to_nothing():
    assert osm_poi.parse_elements({}) == []
    assert osm_poi.parse_elements({"elements": []}) == []


def test_query_covers_every_tag_the_frontend_asked_for():
    q = osm_poi.build_query(44.0, 9.0, 44.5, 9.5)
    for selector in ['["leisure"="marina"]', '["leisure"="slipway"]',
                     '["club"="sailing"]', '["sport"="sailing"]',
                     '["seamark:type"="harbour"]', '["seamark:type"="anchorage"]',
                     '["harbour"="yes"]', '["amenity"="fuel"]["seamark:type"]']:
        assert f"nwr{selector}(44.0,9.0,44.5,9.5);" in q
    assert q.endswith("out center tags;")


# --- the grid ----------------------------------------------------------------

def test_a_coordinate_quantises_to_its_cell_centre():
    assert osm_poi.cell_of(45.3, 9.1) == (45.5, 9.0)
    assert osm_poi.cell_of(-0.1, -0.2) == (-0.0, -0.0)


def test_a_cell_spans_half_a_degree_around_its_centre():
    assert osm_poi.cell_bounds(45.5, 9.0) == (45.25, 8.75, 45.75, 9.25)


def test_every_point_inside_a_cell_maps_back_to_it():
    south, west, north, east = osm_poi.cell_bounds(45.5, 9.0)
    for lat in (south + 0.01, 45.5, north - 0.01):
        for lng in (west + 0.01, 9.0, east - 0.01):
            assert osm_poi.cell_of(lat, lng) == (45.5, 9.0)


def test_a_small_bbox_needs_a_single_cell():
    assert osm_poi.cells_for_bbox(45.3, 9.0, 45.4, 9.1) == [(45.5, 9.0)]


def test_a_bbox_straddling_a_boundary_needs_both_cells():
    cells = osm_poi.cells_for_bbox(45.2, 9.0, 45.3, 9.1)
    assert cells == [(45.0, 9.0), (45.5, 9.0)]


def test_a_wider_bbox_needs_the_whole_rectangle_of_cells():
    cells = osm_poi.cells_for_bbox(44.0, 8.0, 45.0, 9.0)
    assert len(cells) == 9
    assert set(cells) == {(lat, lng) for lat in (44.0, 44.5, 45.0)
                          for lng in (8.0, 8.5, 9.0)}


def test_every_cell_a_bbox_covers_actually_overlaps_it():
    south, west, north, east = 44.9, 8.9, 45.6, 9.4
    for cell_lat, cell_lng in osm_poi.cells_for_bbox(south, west, north, east):
        c_s, c_w, c_n, c_e = osm_poi.cell_bounds(cell_lat, cell_lng)
        assert c_n >= south and c_s <= north and c_e >= west and c_w <= east


def test_bbox_parsing_accepts_a_normal_viewport():
    assert osm_poi.parse_bbox("44.0,9.0,44.5,9.5") == (44.0, 9.0, 44.5, 9.5)


@pytest.mark.parametrize("raw", [
    "", "1,2,3", "1,2,3,4,5", "a,2,3,4",
    "44.5,9.0,44.0,9.5",           # south >= north
    "44.0,9.5,44.5,9.0",           # west >= east
    "-91,9.0,44.5,9.5", "44.0,-181,44.5,9.5",
    "0,0,40,1", "0,0,1,40",        # would sweep the planet
])
def test_absurd_or_malformed_bboxes_are_rejected(raw):
    with pytest.raises(ValueError):
        osm_poi.parse_bbox(raw)


# --- staleness ---------------------------------------------------------------

def test_a_cell_nobody_ever_asked_about_is_filled_on_read():
    assert osm_poi.needs_cold_fill(None, NOW) is True
    assert osm_poi.is_covered(None) is False


def test_a_cell_attempted_but_never_successful_is_still_uncovered():
    cell = _cell(attempted_at=NOW - timedelta(days=3))
    assert osm_poi.is_covered(cell) is False
    assert osm_poi.needs_cold_fill(cell, NOW) is True


def test_a_cell_that_just_failed_is_not_retried_on_read():
    cell = _cell(attempted_at=NOW - timedelta(minutes=5))
    assert osm_poi.needs_cold_fill(cell, NOW) is False
    # ...but is, once the retry window has passed.
    older = _cell(attempted_at=NOW - timedelta(
        minutes=osm_poi.RETRY_AFTER_FAILURE_MIN + 1))
    assert osm_poi.needs_cold_fill(older, NOW) is True


def test_an_expired_cell_is_never_refreshed_on_the_read_path():
    """The non-obvious half of the design: stale marinas are served instantly
    and left to the scheduler, rather than making a user wait on Overpass."""
    at = NOW - timedelta(days=osm_poi.CELL_TTL_DAYS + 1)
    cell = _cell(fetched_at=at, attempted_at=at)
    assert osm_poi.is_covered(cell) is True
    assert osm_poi.needs_cold_fill(cell, NOW) is False
    assert osm_poi.needs_refresh(cell, NOW) is True


def test_a_fresh_cell_is_left_alone_by_both_paths():
    at = NOW - timedelta(days=1)
    cell = _cell(fetched_at=at, attempted_at=at)
    assert osm_poi.needs_cold_fill(cell, NOW) is False
    assert osm_poi.needs_refresh(cell, NOW) is False


def test_a_never_fetched_cell_is_not_the_schedulers_job():
    assert osm_poi.needs_refresh(None, NOW) is False
    assert osm_poi.needs_refresh(_cell(attempted_at=NOW - timedelta(days=9)), NOW) is False


def test_an_expired_cell_that_just_failed_is_not_retried_by_the_scheduler():
    # Oldest-first ordering would otherwise have every run hammer the same
    # few cells while Overpass is down.
    cell = _cell(fetched_at=NOW - timedelta(days=osm_poi.CELL_TTL_DAYS + 1),
                 attempted_at=NOW - timedelta(minutes=5))
    assert osm_poi.needs_refresh(cell, NOW) is False


# --- repository --------------------------------------------------------------

@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[OsmPoiORM.__table__, OsmPoiCellORM.__table__])
    return SqlOsmPoiRepo(sessionmaker(bind=engine, future=True))


BOUNDS = osm_poi.cell_bounds(45.5, 9.0)


def _row(osm_ref, kind="marina", lat=45.5, lng=9.0, name="Porto"):
    return {"osm_ref": osm_ref, "kind": kind, "lat": lat, "lng": lng, "name": name}


def test_a_cell_refresh_is_idempotent(repo):
    rows = [_row("way/1"), _row("node/2", kind="slipway", lat=45.4)]
    assert repo.replace_cell_pois(BOUNDS, rows) == (2, 0, 0)
    assert repo.replace_cell_pois(BOUNDS, rows) == (0, 0, 0)
    assert len(repo.list_in_bbox(*BOUNDS)) == 2


def test_a_refresh_updates_a_moved_or_renamed_poi(repo):
    repo.replace_cell_pois(BOUNDS, [_row("way/1", name="Porto")])
    assert repo.replace_cell_pois(BOUNDS, [_row("way/1", name="Marina Nuova")]) == (0, 1, 0)
    assert repo.list_in_bbox(*BOUNDS)[0].name == "Marina Nuova"


def test_a_poi_overpass_no_longer_returns_is_dropped(repo):
    repo.replace_cell_pois(BOUNDS, [_row("way/1"), _row("way/2")])
    assert repo.replace_cell_pois(BOUNDS, [_row("way/1")]) == (0, 0, 1)
    assert [p.osm_ref for p in repo.list_in_bbox(*BOUNDS)] == ["way/1"]


def test_refreshing_one_cell_does_not_touch_a_neighbours_pois(repo):
    repo.replace_cell_pois(BOUNDS, [_row("way/1")])
    other = osm_poi.cell_bounds(46.0, 9.0)
    repo.replace_cell_pois(other, [_row("way/9", lat=46.0)])
    repo.replace_cell_pois(BOUNDS, [])
    assert [p.osm_ref for p in repo.list_in_bbox(*other)] == ["way/9"]


def test_the_wire_payload_is_exactly_what_the_map_needs(repo):
    repo.replace_cell_pois(BOUNDS, [_row("way/1")])
    assert repo.list_in_bbox(*BOUNDS)[0].to_dict() == {
        "osm_ref": "way/1", "kind": "marina", "lat": 45.5, "lng": 9.0, "name": "Porto",
    }


def test_a_failed_attempt_records_the_attempt_but_leaves_the_cell_uncovered(repo):
    cell = repo.mark_cell(45.5, 9.0, attempted_at=NOW)
    assert cell.fetched_at is None and cell.attempted_at is not None
    assert osm_poi.is_covered(repo.get_cell(45.5, 9.0)) is False


def test_a_successful_fetch_covers_the_cell(repo):
    repo.mark_cell(45.5, 9.0, attempted_at=NOW)
    repo.mark_cell(45.5, 9.0, attempted_at=NOW, fetched_at=NOW)
    assert osm_poi.is_covered(repo.get_cell(45.5, 9.0)) is True


def test_cells_are_looked_up_by_exact_key_not_by_the_lat_lng_rectangle(repo):
    repo.mark_cell(45.5, 9.0, attempted_at=NOW, fetched_at=NOW)
    repo.mark_cell(46.0, 9.5, attempted_at=NOW, fetched_at=NOW)
    found = repo.get_cells([(45.5, 9.0), (46.0, 9.5), (45.5, 9.5)])
    assert set(found) == {(45.5, 9.0), (46.0, 9.5)}


def test_expired_cells_come_back_oldest_first_and_exclude_the_never_fetched(repo):
    repo.mark_cell(45.5, 9.0, attempted_at=NOW, fetched_at=NOW - timedelta(days=90))
    repo.mark_cell(46.0, 9.0, attempted_at=NOW, fetched_at=NOW - timedelta(days=120))
    repo.mark_cell(47.0, 9.0, attempted_at=NOW, fetched_at=NOW - timedelta(days=1))
    repo.mark_cell(48.0, 9.0, attempted_at=NOW)  # never succeeded
    expired = repo.list_expired_cells(before=NOW - timedelta(days=osm_poi.CELL_TTL_DAYS),
                                      limit=osm_poi.MAX_CELLS_PER_REFRESH)
    assert [c.cell_lat for c in expired] == [46.0, 45.5]


# --- cache orchestration -----------------------------------------------------
#
# A hand-rolled fake rather than the SQLite repo above: SQLite drops the
# timezone off a DateTime(timezone=True) round trip (Postgres does not), and
# these are exactly the tests that compare timestamps.

class FakeRepo:
    """Doubles as the ``Repositories`` facade the service is handed and as the
    ``osm_pois`` repo on it — nothing else is reached."""

    def __init__(self, cells=None, fail=()):
        self.osm_pois = self
        self.cells = dict(cells or {})
        self.fail = set(fail)
        self.queried = []
        self.stored = {}

    # the repo half
    def get_cells(self, keys):
        return {k: self.cells[k] for k in keys if k in self.cells}

    def get_cell(self, cell_lat, cell_lng):
        return self.cells.get((cell_lat, cell_lng))

    def mark_cell(self, cell_lat, cell_lng, *, attempted_at, fetched_at=None):
        cell = self.cells.get((cell_lat, cell_lng)) or _cell()
        cell.cell_lat, cell.cell_lng = cell_lat, cell_lng
        cell.attempted_at = attempted_at
        if fetched_at is not None:
            cell.fetched_at = fetched_at
        self.cells[(cell_lat, cell_lng)] = cell
        return cell

    def list_expired_cells(self, before, limit):
        rows = [c for c in self.cells.values()
                if c.fetched_at is not None and c.fetched_at < before]
        return sorted(rows, key=lambda c: c.fetched_at)[:limit]

    def replace_cell_pois(self, bounds, rows):
        self.stored[bounds] = rows
        return (len(rows), 0, 0)

    def list_in_bbox(self, south, west, north, east):
        return []


@pytest.fixture(autouse=True)
def _fresh_breaker():
    """The gate and the circuit breaker are module state, so a test that fails
    a fetch would otherwise pause Overpass for the tests that follow."""
    osm_poi.reset_breaker()
    yield
    osm_poi.reset_breaker()


@pytest.fixture
def overpass(monkeypatch):
    """Stands in for the network. Records every cell queried; a cell listed in
    the repo's ``fail`` set raises, as a down Overpass would."""
    def fake_fetch(cell_lat, cell_lng, deadline=None):
        repo.queried.append((cell_lat, cell_lng))
        if (cell_lat, cell_lng) in repo.fail:
            raise RuntimeError("Overpass unreachable")
        return [_row(f"node/{len(repo.queried)}", lat=cell_lat, lng=cell_lng)]

    repo = None

    def bind(r):
        nonlocal repo
        repo = r
        monkeypatch.setattr(osm_poi, "fetch_cell", fake_fetch)
        return r
    return bind


def test_a_first_visit_fills_its_cells_and_reports_complete_coverage(overpass):
    repo = overpass(FakeRepo())
    out = osm_poi.pois_in_bbox(repo, 45.3, 9.0, 45.4, 9.1)
    assert repo.queried == [(45.5, 9.0)]
    assert out["coverage"] == "complete"


def test_a_cold_fill_is_bounded_and_the_rest_reads_as_partial(overpass):
    repo = overpass(FakeRepo())
    out = osm_poi.pois_in_bbox(repo, 44.0, 8.0, 45.0, 9.0)  # nine cells
    assert len(repo.queried) == osm_poi.MAX_COLD_CELLS_PER_REQUEST
    assert out["coverage"] == "partial"


def test_a_covered_bbox_never_touches_overpass_even_when_stale(overpass):
    stale = NOW - timedelta(days=osm_poi.CELL_TTL_DAYS + 1)
    repo = overpass(FakeRepo({(45.5, 9.0): _cell(fetched_at=stale, attempted_at=stale)}))
    out = osm_poi.pois_in_bbox(repo, 45.3, 9.0, 45.4, 9.1)
    assert repo.queried == []
    assert out["coverage"] == "complete"


def test_a_failed_fill_reports_partial_and_records_the_attempt(overpass):
    repo = overpass(FakeRepo(fail=[(45.5, 9.0)]))
    out = osm_poi.pois_in_bbox(repo, 45.3, 9.0, 45.4, 9.1)
    assert out["coverage"] == "partial"
    cell = repo.get_cell(45.5, 9.0)
    assert cell.fetched_at is None and cell.attempted_at is not None
    # A second request inside the retry window does not ask again.
    osm_poi.pois_in_bbox(repo, 45.3, 9.0, 45.4, 9.1)
    assert repo.queried == [(45.5, 9.0)]


def test_the_refresh_run_takes_the_oldest_cells_and_paces_itself(overpass):
    cells = {(45.0 + i / 2, 9.0): _cell(fetched_at=NOW - timedelta(days=100 + i),
                                        attempted_at=NOW - timedelta(days=100 + i))
             for i in range(7)}
    for key, cell in cells.items():
        cell.cell_lat, cell.cell_lng = key
    repo = overpass(FakeRepo(cells))
    pauses = []
    out = osm_poi.refresh_expired_cells(repo, sleep=pauses.append)
    assert out == {"refreshed": osm_poi.MAX_CELLS_PER_REFRESH, "failed": 0, "skipped": 0}
    assert repo.queried == [(48.0, 9.0), (47.5, 9.0), (47.0, 9.0), (46.5, 9.0), (46.0, 9.0)]
    assert pauses == [osm_poi.PAUSE_BETWEEN_QUERIES_S] * (osm_poi.MAX_CELLS_PER_REFRESH - 1)


def test_the_refresh_run_skips_a_cell_that_just_failed(overpass):
    stale = NOW - timedelta(days=osm_poi.CELL_TTL_DAYS + 1)
    cells = {
        (45.5, 9.0): _cell(fetched_at=stale, attempted_at=datetime.now(timezone.utc)),
        (46.0, 9.0): _cell(fetched_at=stale, attempted_at=stale),
    }
    for key, cell in cells.items():
        cell.cell_lat, cell.cell_lng = key
    repo = overpass(FakeRepo(cells))
    out = osm_poi.refresh_expired_cells(repo, sleep=lambda _: None)
    assert repo.queried == [(46.0, 9.0)]
    assert out == {"refreshed": 1, "failed": 0, "skipped": 1}


def test_a_refresh_that_fails_is_counted_and_leaves_the_old_data_covered(overpass):
    stale = NOW - timedelta(days=osm_poi.CELL_TTL_DAYS + 1)
    cell = _cell(fetched_at=stale, attempted_at=stale)
    cell.cell_lat, cell.cell_lng = 45.5, 9.0
    repo = overpass(FakeRepo({(45.5, 9.0): cell}, fail=[(45.5, 9.0)]))
    out = osm_poi.refresh_expired_cells(repo, sleep=lambda _: None)
    assert out == {"refreshed": 0, "failed": 1, "skipped": 0}
    assert repo.get_cell(45.5, 9.0).fetched_at == stale


# --- read-path refresh (replaces the scheduler for routine freshness) ------

def _cell_at(cell_lat, cell_lng, fetched_at=None, attempted_at=None):
    return SimpleNamespace(cell_lat=cell_lat, cell_lng=cell_lng,
                           fetched_at=fetched_at, attempted_at=attempted_at)


EXPIRED = datetime.now(timezone.utc) - timedelta(days=osm_poi.CELL_TTL_DAYS + 1)
FRESH = datetime.now(timezone.utc)


def test_read_path_refresh_picks_the_expired_cell(overpass):
    """Staleness is handled after the response, not by a scheduler: the cells
    whose age anyone can observe are exactly the ones being looked at."""
    repo = overpass(FakeRepo({
        (45.5, 9.0): _cell_at(45.5, 9.0, fetched_at=FRESH),
        (46.0, 9.0): _cell_at(46.0, 9.0, fetched_at=EXPIRED),
    }))

    assert osm_poi.refresh_stale_cell_in(repo, [(45.5, 9.0), (46.0, 9.0)]) is True
    assert repo.queried == [(46.0, 9.0)]


def test_read_path_refresh_does_one_cell_per_request(overpass):
    """One Overpass query per request at most, which is why it needs no
    pacing sleep the way the batch endpoint does."""
    repo = overpass(FakeRepo({
        (45.5, 9.0): _cell_at(45.5, 9.0, fetched_at=EXPIRED),
        (46.0, 9.0): _cell_at(46.0, 9.0, fetched_at=EXPIRED),
    }))

    osm_poi.refresh_stale_cell_in(repo, [(45.5, 9.0), (46.0, 9.0)])
    assert len(repo.queried) == 1


def test_read_path_refresh_ignores_fresh_and_never_fetched(overpass):
    """A never-fetched cell is the GET's own inline job — refreshing it here
    too would query Overpass twice for one request."""
    repo = overpass(FakeRepo({
        (45.5, 9.0): _cell_at(45.5, 9.0, fetched_at=FRESH),
        (46.0, 9.0): _cell_at(46.0, 9.0, fetched_at=None),
    }))

    assert osm_poi.refresh_stale_cell_in(repo, [(45.5, 9.0), (46.0, 9.0)]) is False
    assert repo.queried == []


def test_read_path_refresh_respects_the_retry_window(overpass):
    """A cell attempted moments ago is left alone, so a down Overpass is not
    re-asked once per page view."""
    repo = overpass(FakeRepo({
        (45.5, 9.0): _cell_at(45.5, 9.0, fetched_at=EXPIRED,
                              attempted_at=datetime.now(timezone.utc)),
    }))

    assert osm_poi.refresh_stale_cell_in(repo, [(45.5, 9.0)]) is False
    assert repo.queried == []


# --- Overpass failure modes ------------------------------------------------
#
# What actually broke in production: Overpass answers a *runtime* error with
# HTTP 200 and a `remark`, so the old code stored zero POIs over a real cell,
# stamped it fetched, and served an empty map there for the whole TTL. The
# rest are the same class of thing — an answer that parses but isn't data.

def test_a_normal_answer_passes_the_payload_check():
    payload = {"elements": [_element(leisure="marina")]}
    assert osm_poi.check_payload(payload) is payload


def test_an_empty_but_honest_answer_is_still_a_success():
    # No marinas in the middle of the Atlantic is a real, cacheable answer.
    assert osm_poi.check_payload({"elements": []}) == {"elements": []}


@pytest.mark.parametrize("remark", [
    "runtime error: Query timed out in 'query' at line 1 after 60 seconds.",
    "runtime error: Query run out of memory in 'recurse' at line 2.",
    "Error: something went wrong",
])
def test_a_runtime_error_returned_as_http_200_is_a_failure(remark):
    with pytest.raises(osm_poi.OverpassError):
        osm_poi.check_payload({"elements": [], "remark": remark})


def test_a_harmless_remark_is_not_treated_as_a_failure():
    payload = {"elements": [], "remark": "Notice: this query returned no data"}
    assert osm_poi.check_payload(payload) is payload


@pytest.mark.parametrize("payload", [{}, {"version": 0.6}, [], None, "<html>"])
def test_a_body_that_is_not_an_overpass_answer_is_a_failure(payload):
    with pytest.raises(osm_poi.OverpassError):
        osm_poi.check_payload(payload)


def test_a_failed_fetch_never_blanks_a_cell_that_already_had_data(overpass):
    """The whole point of the check above: a cell keeps its POIs and its
    ``fetched_at`` when the refetch fails, rather than being emptied."""
    stale = NOW - timedelta(days=osm_poi.CELL_TTL_DAYS + 1)
    cell = _cell(fetched_at=stale, attempted_at=stale)
    cell.cell_lat, cell.cell_lng = 45.5, 9.0
    repo = overpass(FakeRepo({(45.5, 9.0): cell}, fail=[(45.5, 9.0)]))

    osm_poi.refresh_stale_cell_in(repo, [(45.5, 9.0)])

    assert repo.stored == {}  # replace_cell_pois was never reached
    assert repo.get_cell(45.5, 9.0).fetched_at == stale


def test_the_query_asks_overpass_for_no_more_time_than_we_will_wait():
    assert f"[timeout:{osm_poi.QUERY_TIMEOUT_S}]" in osm_poi.build_query(44.0, 9.0, 44.5, 9.5)
    assert "[timeout:9]" in osm_poi.build_query(44.0, 9.0, 44.5, 9.5, timeout_s=9)
    assert osm_poi.QUERY_TIMEOUT_S <= osm_poi.FETCH_TIMEOUT_S


def test_the_read_path_cannot_outlive_the_gateway_timeout():
    """A cold fill is sequential, so its worst case is the budget — not
    cells x endpoints x socket timeout, which is what produced 504s."""
    assert osm_poi.READ_FILL_BUDGET_S < 60


# --- the circuit breaker ---------------------------------------------------
#
# ``may_attempt`` is per cell, which does nothing for an outage: every new
# cell is still a first attempt. Without a global pause, a user panning over
# unfetched coast spends the full budget on every request while Overpass is
# down — and keeps knocking on a service that is rate limiting us.

def _fail(status=None, retry_after=None):
    return osm_poi.OverpassError("nope", status=status, retry_after=retry_after)


def test_overpass_is_called_normally_until_failures_pile_up():
    for _ in range(osm_poi.BREAKER_FAILURES - 1):
        osm_poi._record_failure(_fail())
    assert osm_poi.breaker_blocked_for() == 0


def test_consecutive_failures_pause_the_whole_layer():
    for _ in range(osm_poi.BREAKER_FAILURES):
        osm_poi._record_failure(_fail())
    assert osm_poi.breaker_blocked_for() > 0


def test_a_success_forgets_the_failures_before_it():
    for _ in range(osm_poi.BREAKER_FAILURES - 1):
        osm_poi._record_failure(_fail())
    osm_poi._record_success()
    osm_poi._record_failure(_fail())
    assert osm_poi.breaker_blocked_for() == 0


@pytest.mark.parametrize("status", [429, 504])
def test_being_rate_limited_pauses_immediately_and_for_longer(status):
    """One 429 is enough: continuing to knock is what turns throttling into a
    block, and it is the failure the single shared server IP invites."""
    osm_poi._record_failure(_fail(status=status))
    assert osm_poi.breaker_blocked_for() > osm_poi.BREAKER_COOLDOWN_S


def test_a_retry_after_header_sets_the_pause():
    osm_poi._record_failure(_fail(status=429, retry_after=120))
    assert 60 < osm_poi.breaker_blocked_for() <= 120


def test_a_paused_layer_serves_the_cache_without_calling_overpass(overpass):
    repo = overpass(FakeRepo())
    osm_poi._record_failure(_fail(status=429))

    out = osm_poi.pois_in_bbox(repo, 45.3, 9.0, 45.4, 9.1)

    assert repo.queried == []
    assert out["coverage"] == "partial"
    # And no attempt is recorded against the cell: the pause is about
    # Overpass, not about this place, so it must not also cost the cell its
    # hour-long retry window.
    assert repo.get_cell(45.5, 9.0) is None


def test_the_manual_refresh_lever_clears_the_pause(overpass):
    stale = NOW - timedelta(days=osm_poi.CELL_TTL_DAYS + 1)
    cell = _cell(fetched_at=stale, attempted_at=stale)
    cell.cell_lat, cell.cell_lng = 45.5, 9.0
    repo = overpass(FakeRepo({(45.5, 9.0): cell}))
    osm_poi._record_failure(_fail(status=429))

    out = osm_poi.refresh_expired_cells(repo, sleep=lambda _: None)

    assert repo.queried == [(45.5, 9.0)]
    assert out["refreshed"] == 1


def test_only_one_overpass_query_runs_at_a_time_and_readers_do_not_queue(overpass):
    """Every query now leaves from one server IP. The read path takes the
    slot or serves the cache — it never waits, which is what kept requests
    piling up behind a slow Overpass."""
    repo = overpass(FakeRepo())
    osm_poi._query_gate.acquire()
    try:
        out = osm_poi.pois_in_bbox(repo, 45.3, 9.0, 45.4, 9.1)
    finally:
        osm_poi._query_gate.release()

    assert repo.queried == []
    assert out["coverage"] == "partial"


# --- query_overpass over a faked transport ---------------------------------

class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


@pytest.fixture
def transport(monkeypatch):
    """Replaces ``requests.post``. Returns the list of endpoints called, and
    takes one canned response per attempt."""
    calls = []

    def bind(*responses):
        queue = list(responses)

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            answer = queue.pop(0) if queue else responses[-1]
            if isinstance(answer, Exception):
                raise answer
            return answer

        monkeypatch.setattr(osm_poi.requests, "post", fake_post)
        return calls
    return bind


def test_a_good_answer_comes_back_from_the_first_endpoint(transport):
    calls = transport(FakeResponse(payload={"elements": [_element(leisure="marina")]}))
    out = osm_poi.query_overpass(44.0, 9.0, 44.5, 9.5)
    assert len(out["elements"]) == 1
    assert len(calls) == 1


def test_a_timed_out_query_reported_as_http_200_falls_through_to_the_mirror(transport):
    """The production bug end to end: this used to return the empty body as a
    successful answer, and the caller wiped the cell with it."""
    calls = transport(
        FakeResponse(payload={"elements": [], "remark": "runtime error: Query timed out"}),
        FakeResponse(payload={"elements": [_element(leisure="marina")]}),
    )
    out = osm_poi.query_overpass(44.0, 9.0, 44.5, 9.5)
    assert len(out["elements"]) == 1
    assert [c[0] for c in calls] == list(osm_poi.ENDPOINTS)


def test_every_endpoint_failing_raises_rather_than_returning_nothing(transport):
    transport(FakeResponse(payload={"elements": [], "remark": "runtime error: timed out"}))
    with pytest.raises(osm_poi.OverpassError):
        osm_poi.query_overpass(44.0, 9.0, 44.5, 9.5)


def test_a_rate_limited_answer_is_raised_as_such_with_its_retry_after(transport):
    transport(FakeResponse(status_code=429, text="Too Many Requests",
                           headers={"Retry-After": "42"}))
    with pytest.raises(osm_poi.OverpassError) as excinfo:
        osm_poi.query_overpass(44.0, 9.0, 44.5, 9.5)
    assert excinfo.value.rate_limited
    assert excinfo.value.retry_after == 42


def test_an_html_error_page_served_as_200_is_a_failure(transport):
    transport(FakeResponse(text="<html>Gateway Timeout</html>"))
    with pytest.raises(osm_poi.OverpassError):
        osm_poi.query_overpass(44.0, 9.0, 44.5, 9.5)


def test_each_attempt_gets_only_the_time_that_is_left(transport):
    calls = transport(FakeResponse(payload={"elements": []}))
    osm_poi.query_overpass(44.0, 9.0, 44.5, 9.5, deadline=time.monotonic() + 3)
    assert calls[0][1]["timeout"] <= 3


def test_an_exhausted_deadline_stops_the_endpoint_fallback(transport):
    """Trying the mirror with no time left is how a slow Overpass turned into
    a request that outlived the gateway timeout."""
    calls = transport(FakeResponse(status_code=502, text="bad gateway"))
    with pytest.raises(osm_poi.OverpassError):
        osm_poi.query_overpass(44.0, 9.0, 44.5, 9.5, deadline=time.monotonic() - 1)
    assert calls == []


# --- the endpoint list -----------------------------------------------------
#
# This list is what gets fiddled with whenever Overpass misbehaves, and doing
# it by editing a tuple literal is how the layer once stopped querying
# anything: commenting out all but one entry left a bare parenthesised string,
# so the endpoint loop iterated over its characters and POSTed to "h", to
# "t", ... Every one raised, every one was swallowed as a failed endpoint, and
# no request left the box while the logs blamed Overpass.

def test_no_configuration_means_the_built_in_endpoints():
    assert osm_poi.parse_endpoints(None) == osm_poi.DEFAULT_ENDPOINTS
    assert osm_poi.parse_endpoints("   ") == osm_poi.DEFAULT_ENDPOINTS


@pytest.mark.parametrize("raw", [
    "https://a.example/api/interpreter,https://b.example/api/interpreter",
    "https://a.example/api/interpreter https://b.example/api/interpreter",
    " https://a.example/api/interpreter , https://b.example/api/interpreter ",
])
def test_endpoints_are_separated_by_commas_or_spaces(raw):
    assert osm_poi.parse_endpoints(raw) == ("https://a.example/api/interpreter",
                                            "https://b.example/api/interpreter")


def test_a_single_configured_endpoint_stays_a_list_of_one_url():
    """The regression: one endpoint must be one endpoint, never 39 characters."""
    parsed = osm_poi.parse_endpoints("https://overpass-api.de/api/interpreter")
    assert parsed == ("https://overpass-api.de/api/interpreter",)
    assert list(parsed) == ["https://overpass-api.de/api/interpreter"]


@pytest.mark.parametrize("raw", ["overpass-api.de/api/interpreter", "ftp://x/y",
                                 "https://ok.example/i, nonsense"])
def test_an_unusable_endpoint_list_is_a_startup_error_not_a_silent_outage(raw):
    with pytest.raises(ValueError):
        osm_poi.parse_endpoints(raw)


def test_the_endpoints_actually_in_use_are_whole_urls():
    """Guards the module-level value however it was configured — the shape
    bug was invisible precisely because every element still looked iterable."""
    assert isinstance(osm_poi.ENDPOINTS, tuple)
    assert osm_poi.ENDPOINTS
    for endpoint in osm_poi.ENDPOINTS:
        assert endpoint.startswith("https://")
