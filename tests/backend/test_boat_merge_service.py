"""Resolving a guest-boat claim (``backend/services/boat_merge.py``): the
promote and merge paths ``routers/boats.py``'s approve endpoint delegates to.

Database-free, following ``test_session_detach.py``: in-memory SQLite, the
real ``SqlBoatRepo``, a ``SimpleNamespace`` standing in for the
``Repositories`` facade, ``get_repos`` monkeypatched on ``boat_merge`` itself
(it imports the function directly, not the module, so patching the module
object's attribute is what call sites actually see).
"""

import types
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import (
    BoatClaimORM, BoatClassORM, BoatNoteORM, BoatORM, BoatPhotoORM, DeviceORM,
    LiveRecordingORM, OfficialStandingsORM, PolarPointORM, RegattaEntryORM,
    ResultORM, SessionORM, UserBoatORM,
)
from backend.repositories.sql.boat_repo import SqlBoatRepo
from backend.services import boat_merge

_TABLES = [
    BoatORM.__table__, BoatClassORM.__table__, UserBoatORM.__table__, BoatClaimORM.__table__,
    BoatNoteORM.__table__, BoatPhotoORM.__table__, SessionORM.__table__,
    DeviceORM.__table__, LiveRecordingORM.__table__, PolarPointORM.__table__,
    RegattaEntryORM.__table__, ResultORM.__table__, OfficialStandingsORM.__table__,
]


@pytest.fixture
def repos(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _register_num_nonnulls(dbapi_conn, _):
        dbapi_conn.create_function(
            "num_nonnulls", -1, lambda *args: sum(1 for a in args if a is not None)
        )

    Base.metadata.create_all(engine, tables=_TABLES)
    Session = sessionmaker(bind=engine, future=True)
    repo = types.SimpleNamespace(boats=SqlBoatRepo(Session))
    monkeypatch.setattr(boat_merge, "get_repos", lambda: repo)
    return repo, Session


def _make_boat(Session, *, name="Boat", is_guest=False, guest_created_by=None):
    with Session() as s:
        boat = BoatORM(name=name, is_guest=is_guest, guest_created_by=guest_created_by)
        s.add(boat)
        s.commit()
        return boat.id


# --- promote_guest_boat -------------------------------------------------------

def test_promote_makes_claimant_owner(repos):
    repo, Session = repos
    creator = uuid.uuid4()
    claimant = uuid.uuid4()
    boat_id = _make_boat(Session, is_guest=True, guest_created_by=creator)
    repo.boats.add_member(boat_id, user_id=creator, role="owner")

    boat_merge.promote_guest_boat(boat_id, new_owner_id=claimant, previous_owner_id=creator)

    member = repo.boats.get_member(boat_id, claimant)
    assert member is not None
    assert member.role == "owner"


def test_promote_demotes_previous_owner_to_visitor_not_removed(repos):
    """The creator keeps read access to the sessions they recorded — demoted,
    never dropped from the boat."""
    repo, Session = repos
    creator = uuid.uuid4()
    claimant = uuid.uuid4()
    boat_id = _make_boat(Session, is_guest=True, guest_created_by=creator)
    repo.boats.add_member(boat_id, user_id=creator, role="owner")

    boat_merge.promote_guest_boat(boat_id, new_owner_id=claimant, previous_owner_id=creator)

    creator_member = repo.boats.get_member(boat_id, creator)
    assert creator_member is not None
    assert creator_member.role == "visitor"


def test_promote_clears_guest_flags(repos):
    repo, Session = repos
    creator = uuid.uuid4()
    boat_id = _make_boat(Session, is_guest=True, guest_created_by=creator)
    repo.boats.add_member(boat_id, user_id=creator, role="owner")

    boat_merge.promote_guest_boat(boat_id, new_owner_id=uuid.uuid4(), previous_owner_id=creator)

    boat = repo.boats.get(boat_id)
    assert boat.is_guest is False
    assert boat.guest_created_by is None


def test_promote_when_claimant_already_a_member_upgrades_role(repos):
    """A claimant who happened to already be a visitor on the guest boat gets
    upgraded to owner rather than erroring on a duplicate membership."""
    repo, Session = repos
    creator = uuid.uuid4()
    claimant = uuid.uuid4()
    boat_id = _make_boat(Session, is_guest=True, guest_created_by=creator)
    repo.boats.add_member(boat_id, user_id=creator, role="owner")
    repo.boats.add_member(boat_id, user_id=claimant, role="visitor")

    boat_merge.promote_guest_boat(boat_id, new_owner_id=claimant, previous_owner_id=creator)

    assert repo.boats.get_member(boat_id, claimant).role == "owner"


def test_promote_same_person_claiming_own_guest_boat_stays_owner(repos):
    """``previous_owner_id == new_owner_id`` (a superadmin approved, or the
    creator is somehow also the claimant): must not demote the only owner."""
    repo, Session = repos
    creator = uuid.uuid4()
    boat_id = _make_boat(Session, is_guest=True, guest_created_by=creator)
    repo.boats.add_member(boat_id, user_id=creator, role="owner")

    boat_merge.promote_guest_boat(boat_id, new_owner_id=creator, previous_owner_id=creator)

    assert repo.boats.get_member(boat_id, creator).role == "owner"


# --- merge_boat ---------------------------------------------------------------

def test_merge_boat_raises_when_source_is_not_a_guest_boat(repos):
    """merge_boat deletes the source; doing that to a real (non-guest) boat
    would be unrecoverable, so it must refuse outright."""
    repo, Session = repos
    not_guest = _make_boat(Session, name="Real Boat", is_guest=False)
    target = _make_boat(Session, name="Target")

    with pytest.raises(ValueError, match="Only a guest boat"):
        boat_merge.merge_boat(not_guest, target)

    assert repo.boats.get(not_guest) is not None  # nothing was deleted


def test_merge_boat_raises_on_self_merge(repos):
    repo, Session = repos
    boat_id = _make_boat(Session, is_guest=True)

    with pytest.raises(ValueError, match="itself"):
        boat_merge.merge_boat(boat_id, boat_id)


def test_merge_boat_raises_on_unknown_source(repos):
    repo, Session = repos
    target = _make_boat(Session)

    with pytest.raises(ValueError, match="not found"):
        boat_merge.merge_boat(uuid.uuid4(), target)


def test_merge_boat_raises_on_unknown_target(repos):
    repo, Session = repos
    source = _make_boat(Session, is_guest=True)

    with pytest.raises(ValueError, match="not found"):
        boat_merge.merge_boat(source, uuid.uuid4())


def test_merge_boat_moves_data_and_deletes_the_guest_row(repos):
    repo, Session = repos
    source = _make_boat(Session, name="Guest Boat", is_guest=True)
    target = _make_boat(Session, name="Real Boat")
    with Session() as s:
        row = SessionORM(activity_id=uuid.uuid4(), boat_id=source, status="pending")
        s.add(row)
        s.commit()
        session_id = row.id

    counts = boat_merge.merge_boat(source, target)

    assert counts.get("sessions") == 1
    with Session() as s:
        assert s.get(SessionORM, session_id).boat_id == target
    assert repo.boats.get(source) is None
