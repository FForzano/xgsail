"""Club OSM link suggestions (``services/club_osm_match.py`` + the two new
repo methods behind ``GET /clubs/{id}/osm-suggestions``).

Everything under "matching" and "ranking" is pure and DB-free: no session,
no engine. The repository half (``osm_refs_taken`` / ``list_in_bbox(kind=)``)
runs against an in-memory SQLite engine, following ``test_club_osm_ref.py``
and ``test_osm_poi_cache.py`` — ``backend/routers/`` itself cannot be
imported here (its storage layer wants AWS credentials), which is also why
the manage-gated router endpoint isn't exercised directly; its logic is just
these two repo calls plus ``rank_suggestions``, already covered below.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import ClubORM, OsmPoiCellORM, OsmPoiORM, UserClubORM
from backend.repositories.sql.club_repo import SqlClubRepo
from backend.repositories.sql.osm_poi_repo import SqlOsmPoiRepo
from backend.services import club_osm_match as m
from backend.services.geo import haversine_m


# --- name normalisation / matching -------------------------------------------

def test_significant_tokens_strips_accents_punctuation_and_generic_words():
    assert m.significant_tokens("Società Canottieri Salò") == {"canottieri", "salo"}
    assert m.significant_tokens("CV Barcola-Grignano") == {"cv", "barcola", "grignano"}


def test_a_name_made_only_of_generic_words_has_no_significant_tokens():
    assert m.significant_tokens("Circolo Velico Club Nautico ASD") == set()


def test_purely_generic_names_never_match_anything():
    # No distinguishing evidence on either side (or one side) -> never a match.
    assert m.name_similarity("Circolo Velico Club", None) == 0.0
    assert m.name_similarity("Circolo Velico Club", "Circolo Velico Foo Bar") == 0.0
    assert m.names_match(None, "Circolo Velico Barcola") is False


@pytest.mark.parametrize("a,b", [
    ("Società Canottieri Salò", "Societa Canottieri Salo"),           # accents
    ("Circolo Velico Barcola Grignano", "CV Barcola-Grignano"),       # abbreviation + hyphen, drops generic words
    ("Circolo Nautico Ravennate", "Circolo Nautico Ravenate"),        # plausible OSM typo
    ("Circolo Nautico Anzio", "Lega Navale Anzio"),                   # different wording, same place name
])
def test_names_that_denote_the_same_club_match(a, b):
    assert m.names_match(a, b) is True
    assert m.name_similarity(a, b) == m.name_similarity(b, a)  # symmetric


@pytest.mark.parametrize("a,b", [
    ("Circolo Velico Rimini", "Canottieri Andrea Doria"),
    ("Yacht Club Marina di Ravenna", "Circolo Nautico Adriatico"),
])
def test_two_different_clubs_in_the_same_town_do_not_match(a, b):
    assert m.names_match(a, b) is False


# --- bbox_for_radius ----------------------------------------------------------

def test_bbox_encloses_a_point_at_the_radius_due_north_and_east():
    lat, lng, radius = 45.0, 9.0, m.SUGGESTION_RADIUS_M
    south, west, north, east = m.bbox_for_radius(lat, lng, radius_m=radius)
    # A point exactly `radius` north (same lng) must fall on/inside the box,
    # allowing the same small margin the spherical-vs-box math leaves.
    assert haversine_m(lat, lng, north, lng) >= radius - 5
    assert haversine_m(lat, lng, lat, east) >= radius - 5
    assert south < lat < north
    assert west < lng < east


def test_bbox_stays_within_valid_lat_lng_near_a_pole():
    south, west, north, east = m.bbox_for_radius(89.9, 9.0)
    assert -90.0 <= south <= north <= 90.0
    assert -180.0 <= west <= east <= 180.0


# --- rank_suggestions -----------------------------------------------------------

def _poi(osm_ref, kind="sailing_club", lat=45.0, lng=9.0, name=None):
    return SimpleNamespace(osm_ref=osm_ref, kind=kind, lat=lat, lng=lng, name=name)


CLUB_LAT, CLUB_LNG = 45.0, 9.0


def test_only_sailing_club_kind_pois_are_suggested():
    pois = [
        _poi("way/1", kind="marina", name="Circolo Velico Test"),
        _poi("way/2", kind="sailing_club", name="Circolo Velico Test"),
    ]
    out = m.rank_suggestions(CLUB_LAT, CLUB_LNG, "Circolo Velico Test", pois, taken_refs=set())
    assert [s["osm_ref"] for s in out] == ["way/2"]


def test_radius_cutoff_just_inside_vs_just_outside():
    # ~1990m north (inside 2km) and ~2010m north (outside).
    inside_lat = CLUB_LAT + 1990 / 111_320
    outside_lat = CLUB_LAT + 2010 / 111_320
    pois = [
        _poi("way/in", lat=inside_lat, lng=CLUB_LNG, name="Circolo Test"),
        _poi("way/out", lat=outside_lat, lng=CLUB_LNG, name="Circolo Test"),
    ]
    out = m.rank_suggestions(CLUB_LAT, CLUB_LNG, "Circolo Test", pois, taken_refs=set())
    assert [s["osm_ref"] for s in out] == ["way/in"]


def test_taken_refs_are_excluded():
    pois = [_poi("way/1", name="Circolo Test")]
    out = m.rank_suggestions(CLUB_LAT, CLUB_LNG, "Circolo Test", pois, taken_refs={"way/1"})
    assert out == []


def test_an_unnamed_poi_is_still_suggested_with_name_match_false():
    pois = [_poi("way/1", name=None)]
    out = m.rank_suggestions(CLUB_LAT, CLUB_LNG, "Circolo Velico Test", pois, taken_refs=set())
    assert len(out) == 1
    assert out[0]["name_match"] is False
    assert out[0]["osm_ref"] == "way/1"


def test_a_poi_with_no_position_is_skipped():
    pois = [_poi("way/1", lat=None, lng=CLUB_LNG, name="Circolo Test"),
           _poi("way/2", lat=CLUB_LAT, lng=None, name="Circolo Test")]
    out = m.rank_suggestions(CLUB_LAT, CLUB_LNG, "Circolo Test", pois, taken_refs=set())
    assert out == []


def test_a_similar_name_farther_away_beats_a_dissimilar_one_nearby():
    near_lat = CLUB_LAT + 100 / 111_320
    far_lat = CLUB_LAT + 1500 / 111_320
    pois = [
        _poi("way/near", lat=near_lat, lng=CLUB_LNG, name="Canottieri Andrea Doria"),
        _poi("way/far", lat=far_lat, lng=CLUB_LNG, name="Circolo Velico Rimini"),
    ]
    out = m.rank_suggestions(CLUB_LAT, CLUB_LNG, "Circolo Velico Rimini", pois, taken_refs=set())
    assert [s["osm_ref"] for s in out] == ["way/far", "way/near"]


def test_among_equally_similar_names_the_closer_one_wins():
    near_lat = CLUB_LAT + 100 / 111_320
    far_lat = CLUB_LAT + 1500 / 111_320
    pois = [
        _poi("way/far", lat=far_lat, lng=CLUB_LNG, name="Circolo Velico Rimini"),
        _poi("way/near", lat=near_lat, lng=CLUB_LNG, name="Circolo Velico Rimini"),
    ]
    out = m.rank_suggestions(CLUB_LAT, CLUB_LNG, "Circolo Velico Rimini", pois, taken_refs=set())
    assert [s["osm_ref"] for s in out] == ["way/near", "way/far"]


def test_results_are_capped_at_max_suggestions():
    pois = [_poi(f"way/{i}", lat=CLUB_LAT + i / 111_320, name="Circolo Test")
           for i in range(m.MAX_SUGGESTIONS + 3)]
    out = m.rank_suggestions(CLUB_LAT, CLUB_LNG, "Circolo Test", pois, taken_refs=set())
    assert len(out) == m.MAX_SUGGESTIONS


def test_payload_carries_exactly_the_seven_contract_keys():
    pois = [_poi("way/1", name="Circolo Test")]
    out = m.rank_suggestions(CLUB_LAT, CLUB_LNG, "Circolo Test", pois, taken_refs=set())
    assert len(out) == 1
    assert set(out[0]) == {"osm_ref", "name", "kind", "lat", "lng", "distance_m", "name_match"}


def test_no_pois_and_no_club_name_both_yield_no_suggestions():
    assert m.rank_suggestions(CLUB_LAT, CLUB_LNG, None, [], taken_refs=set()) == []
    assert m.rank_suggestions(CLUB_LAT, CLUB_LNG, "Circolo Test", [], taken_refs=set()) == []


# --- repository: SqlClubRepo.osm_refs_taken -----------------------------------

@pytest.fixture
def club_repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ClubORM.__table__, UserClubORM.__table__])
    return SqlClubRepo(sessionmaker(bind=engine, future=True))


def test_osm_refs_taken_of_an_empty_list_is_empty_with_no_query(club_repo, monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("should not touch the session for an empty list")
    monkeypatch.setattr(club_repo, "Session", _boom)
    assert club_repo.osm_refs_taken([]) == set()


def test_osm_refs_taken_returns_only_the_refs_actually_held(club_repo):
    club_repo.create({"name": "CV Uno", "osm_ref": "way/1"})
    club_repo.create({"name": "CV Due", "osm_ref": "way/2"})
    club_repo.create({"name": "CV Tre"})  # no osm_ref
    taken = club_repo.osm_refs_taken(["way/1", "way/2", "way/3", "way/99"])
    assert taken == {"way/1", "way/2"}


# --- repository: SqlOsmPoiRepo.list_in_bbox(kind=) ----------------------------

@pytest.fixture
def poi_repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[OsmPoiORM.__table__, OsmPoiCellORM.__table__])
    return SqlOsmPoiRepo(sessionmaker(bind=engine, future=True))


BOUNDS = (44.5, 8.5, 45.5, 9.5)


def _row(osm_ref, kind="sailing_club", lat=45.0, lng=9.0, name="Circolo"):
    return {"osm_ref": osm_ref, "kind": kind, "lat": lat, "lng": lng, "name": name}


def test_list_in_bbox_with_no_kind_returns_everything(poi_repo):
    poi_repo.replace_cell_pois(BOUNDS, [_row("way/1", kind="marina"),
                                        _row("way/2", kind="sailing_club")])
    assert {p.osm_ref for p in poi_repo.list_in_bbox(*BOUNDS)} == {"way/1", "way/2"}


def test_list_in_bbox_with_a_kind_filters_to_it(poi_repo):
    poi_repo.replace_cell_pois(BOUNDS, [_row("way/1", kind="marina"),
                                        _row("way/2", kind="sailing_club")])
    out = poi_repo.list_in_bbox(*BOUNDS, kind="sailing_club")
    assert [p.osm_ref for p in out] == ["way/2"]
