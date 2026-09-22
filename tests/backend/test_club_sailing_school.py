"""A club's sailing school: ``clubs.has_sailing_school`` (authoritative,
manager-set) and ``clubs.school_osm_ref`` (which separate OSM element it is),
plus the OSM-cache evidence that proposes a value for a manager to confirm.

Three things, following the split in ``test_club_osm_ref.py`` /
``test_osm_poi_cache.py``:

- ``services/osm_poi.has_sailing_school`` — the one derivation of "does this
  element teach", pure over ``(kind, tags)``.
- ``services/club_osm_match.normalise_school_changes`` /
  ``school_suggestion`` / ``no_school_suggestion`` — pure functions, no DB.
- ``SqlClubRepo`` — persistence of both new columns, and the widened
  ``get_by_osm_ref``/``osm_refs_taken`` lookups, against an in-memory SQLite
  engine (``backend/routers/`` cannot be imported here — its storage layer
  wants AWS credentials).
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import ClubORM, UserClubORM
from backend.repositories.sql.club_repo import SqlClubRepo
from backend.services import club_osm_match, osm_poi


def _poi(osm_ref="way/1", kind="sailing_school", lat=45.0, lng=9.0,
         name="Scuola Vela", tags=None):
    return SimpleNamespace(osm_ref=osm_ref, kind=kind, lat=lat, lng=lng,
                            name=name, tags=tags)


# --- has_sailing_school derivation ------------------------------------------

def test_cnv_style_tags_derive_true():
    tags = {
        "club": "sport",
        "sport": "sailing;kitesurfing;sup;kayak;parasailing;windsurf;wingfoil",
        "amenity": "sailing_school;boat_storage",
    }
    assert osm_poi.has_sailing_school("sailing_club", tags) is True


def test_null_tags_on_sailing_club_kind_derive_false():
    """The pre-0059 transitional state: rows cached before tags were stored
    have ``tags=None``. "We don't know" must not render as a badge."""
    assert osm_poi.has_sailing_school("sailing_club", None) is False


def test_null_tags_on_sailing_school_kind_derive_true():
    """The kind itself is evidence enough, and it's the only evidence left on
    a row with no tags."""
    assert osm_poi.has_sailing_school("sailing_school", None) is True


def test_marina_with_no_school_tag_derives_false():
    assert osm_poi.has_sailing_school("marina", {"leisure": "marina"}) is False


def test_poi_payload_adds_has_school_without_exposing_tags():
    orm = SimpleNamespace(
        kind="sailing_school", tags={"amenity": "sailing_school"},
        to_dict=lambda: {"osm_ref": "way/1", "kind": "sailing_school",
                          "lat": 45.0, "lng": 9.0, "name": "Scuola"},
    )
    payload = osm_poi.poi_payload(orm)
    assert payload["has_school"] is True
    assert "tags" not in payload


# --- normalise_school_changes ------------------------------------------------

def test_setting_ref_implies_the_flag():
    out = club_osm_match.normalise_school_changes({"school_osm_ref": "way/1"})
    assert out == {"school_osm_ref": "way/1", "has_sailing_school": True}


def test_clearing_the_flag_clears_the_ref():
    out = club_osm_match.normalise_school_changes({"has_sailing_school": False})
    assert out == {"has_sailing_school": False, "school_osm_ref": None}


def test_clearing_the_flag_overrides_a_ref_set_in_the_same_body_when_not_flagged():
    # has_sailing_school False + no ref in the body: ref gets cleared.
    out = club_osm_match.normalise_school_changes({"has_sailing_school": False,
                                                     "name": "CV Test"})
    assert out["school_osm_ref"] is None
    assert out["has_sailing_school"] is False


def test_setting_ref_to_none_does_not_force_the_flag():
    out = club_osm_match.normalise_school_changes({"school_osm_ref": None})
    assert out == {"school_osm_ref": None}


def test_empty_changes_pass_through_untouched():
    assert club_osm_match.normalise_school_changes({}) == {}


def test_unrelated_fields_pass_through_untouched():
    changes = {"name": "CV Test", "website": "https://example.org"}
    assert club_osm_match.normalise_school_changes(changes) == changes


def test_contradictory_body_raises():
    with pytest.raises(club_osm_match.SchoolFieldsConflict):
        club_osm_match.normalise_school_changes(
            {"school_osm_ref": "way/1", "has_sailing_school": False}
        )


def test_normalise_does_not_mutate_its_input():
    changes = {"school_osm_ref": "way/1"}
    club_osm_match.normalise_school_changes(changes)
    assert changes == {"school_osm_ref": "way/1"}


# --- school_suggestion --------------------------------------------------------

def test_linked_wins_over_nearby():
    linked = _poi(osm_ref="way/1", kind="sailing_school", tags=None)
    nearby = [_poi(osm_ref="way/2", kind="sailing_school", lat=45.001, lng=9.001)]
    out = club_osm_match.school_suggestion(linked, nearby, club_lat=45.0, club_lng=9.0)
    assert out["source"] == "linked"
    assert [c["osm_ref"] for c in out["candidates"]] == ["way/1"]


def test_linked_candidate_has_no_distance():
    linked = _poi(osm_ref="way/1", kind="sailing_school")
    out = club_osm_match.school_suggestion(linked, [], club_lat=45.0, club_lng=9.0)
    assert out["candidates"][0]["distance_m"] is None


def test_linked_element_not_qualifying_falls_through_to_nearby():
    linked = _poi(osm_ref="way/1", kind="sailing_club", tags=None)
    nearby = [_poi(osm_ref="way/2", kind="sailing_school", lat=45.001, lng=9.0)]
    out = club_osm_match.school_suggestion(linked, nearby, club_lat=45.0, club_lng=9.0)
    assert out["source"] == "nearby"


def test_nearby_within_radius_is_a_candidate():
    # ~0.0025 deg lat ~= 277m, just inside 300m.
    nearby = [_poi(osm_ref="way/2", kind="sailing_school", lat=45.0025, lng=9.0)]
    out = club_osm_match.school_suggestion(None, nearby, club_lat=45.0, club_lng=9.0)
    assert out["source"] == "nearby"
    assert out["candidates"][0]["osm_ref"] == "way/2"


def test_nearby_just_outside_radius_is_excluded():
    # ~0.004 deg lat ~= 445m, outside 300m.
    nearby = [_poi(osm_ref="way/2", kind="sailing_school", lat=45.004, lng=9.0)]
    out = club_osm_match.school_suggestion(None, nearby, club_lat=45.0, club_lng=9.0)
    assert out == club_osm_match.no_school_suggestion()


def test_other_kind_inside_radius_is_never_a_candidate():
    nearby = [_poi(osm_ref="way/2", kind="marina", lat=45.001, lng=9.0)]
    out = club_osm_match.school_suggestion(None, nearby, club_lat=45.0, club_lng=9.0)
    assert out["source"] is None


def test_clubs_own_linked_element_excluded_from_nearby_scan():
    linked = _poi(osm_ref="way/1", kind="sailing_club", tags=None)
    nearby = [_poi(osm_ref="way/1", kind="sailing_school", lat=45.0, lng=9.0)]
    out = club_osm_match.school_suggestion(linked, nearby, club_lat=45.0, club_lng=9.0)
    assert out["source"] is None


def test_candidates_sorted_nearest_first_and_capped():
    nearby = [
        _poi(osm_ref="way/far", kind="sailing_school", lat=45.0020, lng=9.0),
        _poi(osm_ref="way/near", kind="sailing_school", lat=45.0005, lng=9.0),
        _poi(osm_ref="way/mid", kind="sailing_school", lat=45.0012, lng=9.0),
        _poi(osm_ref="way/extra1", kind="sailing_school", lat=45.0015, lng=9.0),
        _poi(osm_ref="way/extra2", kind="sailing_school", lat=45.0018, lng=9.0),
    ]
    out = club_osm_match.school_suggestion(None, nearby, club_lat=45.0, club_lng=9.0)
    assert out["source"] == "nearby"
    refs = [c["osm_ref"] for c in out["candidates"]]
    assert len(refs) == club_osm_match.MAX_SCHOOL_SUGGESTIONS
    assert refs == ["way/near", "way/mid", "way/extra1"]
    distances = [c["distance_m"] for c in out["candidates"]]
    assert distances == sorted(distances)


def test_missing_club_coordinates_returns_empty_answer():
    nearby = [_poi(osm_ref="way/2", kind="sailing_school", lat=45.0, lng=9.0)]
    out = club_osm_match.school_suggestion(None, nearby, club_lat=None, club_lng=None)
    assert out == club_osm_match.no_school_suggestion()


def test_no_school_suggestion_is_a_fresh_object_each_call():
    a = club_osm_match.no_school_suggestion()
    b = club_osm_match.no_school_suggestion()
    assert a == b
    assert a is not b
    a["candidates"].append({"osm_ref": "way/999"})
    assert b["candidates"] == []


# --- repository ---------------------------------------------------------------

@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ClubORM.__table__, UserClubORM.__table__])
    return SqlClubRepo(sessionmaker(bind=engine, future=True))


def test_update_persists_both_new_fields(repo):
    """The ``allowed``-tuple trap: a field missing from ``SqlClubRepo.update``'s
    allow-list is silently ignored on PATCH."""
    club = repo.create({"name": "CV Uno"})
    updated = repo.update(club.id, {"has_sailing_school": True,
                                     "school_osm_ref": "way/777"})
    assert updated.has_sailing_school is True
    assert updated.school_osm_ref == "way/777"
    reloaded = repo.get(club.id)
    assert reloaded.has_sailing_school is True
    assert reloaded.school_osm_ref == "way/777"


def test_get_by_osm_ref_finds_by_either_column(repo):
    is_club = repo.create({"name": "CV Is", "osm_ref": "way/1"})
    school_club = repo.create({"name": "CV School", "school_osm_ref": "way/2"})
    assert repo.get_by_osm_ref("way/1").id == is_club.id
    assert repo.get_by_osm_ref("way/2").id == school_club.id


def test_osm_refs_taken_reports_refs_in_either_column(repo):
    repo.create({"name": "CV Is", "osm_ref": "way/1"})
    repo.create({"name": "CV School", "school_osm_ref": "way/2"})
    taken = repo.osm_refs_taken(["way/1", "way/2", "way/3"])
    assert taken == {"way/1", "way/2"}


def test_club_with_neither_ref_set_never_matches_a_null_lookup(repo):
    """Same class of bug as ``get_entry(regatta_id, None)`` in CLAUDE.md: a
    club with no OSM link at all must not pair up with a NULL comparison."""
    repo.create({"name": "CV Neither"})
    other = repo.create({"name": "CV Other"})
    assert repo.osm_refs_taken([]) == set()
    # A club with neither column set must not surface from a real lookup
    # either, even though both its columns are NULL in the DB.
    for ref in ("way/1", "node/1", "relation/1"):
        holder = repo.get_by_osm_ref(ref)
        assert holder is None or holder.id == other.id


# --- model ---------------------------------------------------------------------

def test_school_osm_ref_is_unique(repo):
    repo.create({"name": "CV Uno", "school_osm_ref": "way/999"})
    with pytest.raises(IntegrityError):
        repo.create({"name": "CV Due", "school_osm_ref": "way/999"})


def test_has_sailing_school_defaults_false_on_plain_create(repo):
    club = repo.create({"name": "CV Plain"})
    assert club.has_sailing_school is False
    assert club.school_osm_ref is None
