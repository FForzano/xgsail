"""``SqlBoatRepo.find_guest_matches`` — proactive claim-suggestion matching on
(boat class, sail number).

Database-free, following ``test_boat_claims_repo.py``: an in-memory SQLite
engine, real repositories, only the tables the code under test actually
touches.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import BoatClaimORM, BoatClassORM, BoatORM, UserBoatORM
from backend.repositories.sql.boat_repo import SqlBoatRepo

_TABLES = [
    BoatORM.__table__, BoatClassORM.__table__, UserBoatORM.__table__, BoatClaimORM.__table__,
]


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=_TABLES)
    Session = sessionmaker(bind=engine, future=True)
    return SqlBoatRepo(Session), Session


def _make_class(Session, *, name="470"):
    with Session() as s:
        cls = BoatClassORM(name=name)
        s.add(cls)
        s.commit()
        return cls.id


def _make_boat(Session, *, name="Boat", is_guest=False, guest_created_by=None,
               boat_class_id=None, sail_number=None):
    with Session() as s:
        boat = BoatORM(name=name, is_guest=is_guest, guest_created_by=guest_created_by,
                       boat_class_id=boat_class_id, sail_number=sail_number)
        s.add(boat)
        s.commit()
        return boat.id


def _own(Session, *, boat_id, user_id, role="owner"):
    with Session() as s:
        s.add(UserBoatORM(boat_id=boat_id, user_id=user_id, role=role))
        s.commit()


def test_normalised_sail_number_match_is_found(repo):
    r, Session = repo
    user_id = uuid.uuid4()
    class_id = _make_class(Session)
    my_boat = _make_boat(Session, name="My Boat", boat_class_id=class_id,
                         sail_number="ITA-1234")
    _own(Session, boat_id=my_boat, user_id=user_id)
    guest_boat = _make_boat(Session, name="Guest Boat", is_guest=True,
                            boat_class_id=class_id, sail_number="ita 1234",
                            guest_created_by=uuid.uuid4())

    result = r.find_guest_matches(user_id)

    assert [(g.id, m.id) for g, m in result] == [(guest_boat, my_boat)]


def test_same_sail_number_different_class_does_not_match(repo):
    r, Session = repo
    user_id = uuid.uuid4()
    class_a = _make_class(Session, name="470")
    class_b = _make_class(Session, name="Laser")
    my_boat = _make_boat(Session, boat_class_id=class_a, sail_number="ITA1234")
    _own(Session, boat_id=my_boat, user_id=user_id)
    _make_boat(Session, is_guest=True, boat_class_id=class_b, sail_number="ITA1234",
              guest_created_by=uuid.uuid4())

    assert r.find_guest_matches(user_id) == []


def test_null_or_blank_sail_number_never_matches(repo):
    r, Session = repo
    user_id = uuid.uuid4()
    class_id = _make_class(Session)
    # My boat has no sail number at all.
    my_boat_no_sail = _make_boat(Session, boat_class_id=class_id, sail_number=None)
    _own(Session, boat_id=my_boat_no_sail, user_id=user_id)
    _make_boat(Session, is_guest=True, boat_class_id=class_id, sail_number=None,
              guest_created_by=uuid.uuid4())
    _make_boat(Session, is_guest=True, boat_class_id=class_id, sail_number="   ",
              guest_created_by=uuid.uuid4())

    assert r.find_guest_matches(user_id) == []

    # My boat has a real sail number, but the guest boat's is blank.
    my_boat = _make_boat(Session, boat_class_id=class_id, sail_number="ITA1234")
    _own(Session, boat_id=my_boat, user_id=user_id)
    _make_boat(Session, is_guest=True, boat_class_id=class_id, sail_number="",
              guest_created_by=uuid.uuid4())

    assert r.find_guest_matches(user_id) == []


def test_null_class_never_matches(repo):
    r, Session = repo
    user_id = uuid.uuid4()
    my_boat = _make_boat(Session, boat_class_id=None, sail_number="ITA1234")
    _own(Session, boat_id=my_boat, user_id=user_id)
    _make_boat(Session, is_guest=True, boat_class_id=None, sail_number="ITA1234",
              guest_created_by=uuid.uuid4())

    assert r.find_guest_matches(user_id) == []


def test_excludes_guest_boat_the_caller_already_belongs_to(repo):
    r, Session = repo
    user_id = uuid.uuid4()
    class_id = _make_class(Session)
    my_boat = _make_boat(Session, boat_class_id=class_id, sail_number="ITA1234")
    _own(Session, boat_id=my_boat, user_id=user_id)
    guest_boat = _make_boat(Session, is_guest=True, boat_class_id=class_id,
                            sail_number="ITA1234", guest_created_by=uuid.uuid4())
    # The caller created this guest boat themselves - already a member.
    _own(Session, boat_id=guest_boat, user_id=user_id, role="owner")

    assert r.find_guest_matches(user_id) == []


def test_excludes_guest_boat_with_pending_claim_but_not_rejected(repo):
    r, Session = repo
    user_id = uuid.uuid4()
    class_id = _make_class(Session)
    my_boat = _make_boat(Session, boat_class_id=class_id, sail_number="ITA1234")
    _own(Session, boat_id=my_boat, user_id=user_id)
    guest_boat = _make_boat(Session, is_guest=True, boat_class_id=class_id,
                            sail_number="ITA1234", guest_created_by=uuid.uuid4())

    claim = r.create_claim(guest_boat, user_id=user_id)
    assert r.find_guest_matches(user_id) == []

    r.resolve_claim(claim.id, status="rejected", resolved_by=uuid.uuid4())

    result = r.find_guest_matches(user_id)
    assert [(g.id, m.id) for g, m in result] == [(guest_boat, my_boat)]
