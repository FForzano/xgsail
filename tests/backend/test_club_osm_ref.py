"""``clubs.osm_ref`` — the link between an XGSail club and the OpenStreetMap
element it *is*, which lets the explorer map stop drawing the same club twice.

Two halves, both database-free in the sense the suite means it (no Postgres):
- the format validator on ``ClubWriteModel``, pure Pydantic;
- the uniqueness lookup ``SqlClubRepo.get_by_osm_ref`` against an in-memory
  SQLite engine with the ``clubs`` table (plus ``user_clubs``, which
  ``ClubORM.members`` eagerly selects), following
  ``test_boat_claims_repo.py``.

``backend/routers/clubs.py`` cannot be imported here (its storage layer needs
AWS credentials), so the router's conflict rule is expressed as the one
comparison it makes on the repo's result — ``holder is not None and
holder.id != club_id`` — which is what distinguishes "another club holds this
ref" (409) from "this club is re-setting its own" (fine).
"""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import ClubORM, UserClubORM
from backend.repositories.sql.club_repo import SqlClubRepo
from backend.schemas.club import ClubWriteModel


# --- format validation -------------------------------------------------------

@pytest.mark.parametrize("ref", ["node/1", "way/123", "relation/9", "way/123456"])
def test_valid_osm_refs_are_accepted(ref):
    assert ClubWriteModel(osm_ref=ref).osm_ref == ref


@pytest.mark.parametrize(
    "ref", ["", "way", "way/", "way/abc", "way/-1", "way/0", "foo/1", "/1",
            "way/1/2", " way/1", "WAY/1"],
)
def test_malformed_osm_refs_are_rejected(ref):
    with pytest.raises(ValidationError):
        ClubWriteModel(osm_ref=ref)


def test_osm_ref_is_optional_and_defaults_to_none():
    body = ClubWriteModel(name="CV Test")
    assert body.osm_ref is None
    assert "osm_ref" not in body.model_fields_set


def test_explicit_null_osm_ref_unlinks_rather_than_failing():
    body = ClubWriteModel(osm_ref=None)
    assert body.osm_ref is None
    assert "osm_ref" in body.model_fields_set


# --- uniqueness / conflict ---------------------------------------------------

@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ClubORM.__table__, UserClubORM.__table__])
    return SqlClubRepo(sessionmaker(bind=engine, future=True))


def _conflicts(repo, osm_ref, club_id=None) -> bool:
    """The router's rule: another club already holds the ref."""
    holder = repo.get_by_osm_ref(osm_ref)
    return holder is not None and holder.id != club_id


def test_osm_ref_is_null_by_default(repo):
    club = repo.create({"name": "CV Senza OSM"})
    assert club.osm_ref is None
    assert repo.get_by_osm_ref("way/1") is None


def test_osm_ref_reaches_the_wire_payload(repo):
    club = repo.create({"name": "CV Wire", "osm_ref": "way/42"})
    assert repo.get(club.id).to_dict()["osm_ref"] == "way/42"


def test_lookup_finds_the_club_holding_the_ref(repo):
    club = repo.create({"name": "CV Uno", "osm_ref": "node/98765"})
    assert repo.get_by_osm_ref("node/98765").id == club.id


def test_resetting_a_clubs_own_osm_ref_is_not_a_conflict(repo):
    club = repo.create({"name": "CV Uno", "osm_ref": "way/123456"})
    assert _conflicts(repo, "way/123456", club_id=club.id) is False


def test_another_clubs_osm_ref_is_a_conflict(repo):
    repo.create({"name": "CV Uno", "osm_ref": "way/123456"})
    other = repo.create({"name": "CV Due"})
    assert _conflicts(repo, "way/123456", club_id=other.id) is True
    # create has no club id of its own yet
    assert _conflicts(repo, "way/123456") is True


def test_unclaimed_ref_is_free_for_anyone(repo):
    other = repo.create({"name": "CV Due"})
    assert _conflicts(repo, "relation/9", club_id=other.id) is False


def test_update_can_set_and_clear_osm_ref(repo):
    club = repo.create({"name": "CV Uno"})
    assert repo.update(club.id, {"osm_ref": "node/5"}).osm_ref == "node/5"
    assert repo.update(club.id, {"osm_ref": None}).osm_ref is None
