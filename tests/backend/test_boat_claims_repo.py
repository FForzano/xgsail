"""Guest boats + ``boat_claims`` repository behaviour
(``backend/repositories/sql/boat_repo.py``).

Database-free, following ``test_boat_notebook.py``/``test_session_detach.py``:
an in-memory SQLite engine, real repositories, only the tables the code under
test actually touches. ``merge_into`` unconditionally issues SQL against every
table a boat can be referenced from (regatta entries, results, official
standings, devices, live recordings, polar points, photos, notes, claims,
sessions), so all of those must exist even though most tests leave them empty
— and two of them (``devices``, ``polar_points``) carry a Postgres-only
``num_nonnulls()`` CHECK, registered here as a SQLite user function so
``CREATE TABLE`` succeeds.
"""

import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import (
    BoatClaimORM,
    BoatClassORM,
    BoatNoteORM,
    BoatORM,
    BoatPhotoORM,
    DeviceORM,
    LiveRecordingORM,
    OfficialStandingsORM,
    PolarPointORM,
    RegattaEntryORM,
    ResultORM,
    SessionORM,
    UserBoatORM,
)
from backend.repositories.sql.boat_repo import SqlBoatRepo

_TABLES = [
    BoatORM.__table__, BoatClassORM.__table__, UserBoatORM.__table__, BoatClaimORM.__table__,
    BoatNoteORM.__table__, BoatPhotoORM.__table__, SessionORM.__table__,
    DeviceORM.__table__, LiveRecordingORM.__table__, PolarPointORM.__table__,
    RegattaEntryORM.__table__, ResultORM.__table__, OfficialStandingsORM.__table__,
]


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _register_num_nonnulls(dbapi_conn, _):
        dbapi_conn.create_function(
            "num_nonnulls", -1, lambda *args: sum(1 for a in args if a is not None)
        )

    Base.metadata.create_all(engine, tables=_TABLES)
    Session = sessionmaker(bind=engine, future=True)
    return SqlBoatRepo(Session), Session


def _make_boat(Session, *, name="Boat", is_guest=False, guest_created_by=None):
    with Session() as s:
        boat = BoatORM(name=name, is_guest=is_guest, guest_created_by=guest_created_by)
        s.add(boat)
        s.commit()
        return boat.id


def _make_session(Session, *, boat_id):
    """Just enough of a ``sessions`` row for merge_into's boat_id re-point —
    activity_id's FK target table isn't created, but SQLite doesn't enforce
    FKs unless PRAGMA foreign_keys=ON, which nothing here turns on."""
    with Session() as s:
        row = SessionORM(activity_id=uuid.uuid4(), boat_id=boat_id, status="pending")
        s.add(row)
        s.commit()
        return row.id


# --- guest boats are excluded from the public picker ------------------------

def test_list_excludes_guest_boats_by_default(repo):
    r, Session = repo
    _make_boat(Session, name="Real Boat")
    _make_boat(Session, name="Guest Boat", is_guest=True, guest_created_by=uuid.uuid4())

    result = r.list()

    assert [b.name for b in result] == ["Real Boat"]


def test_list_include_guest_true_returns_both(repo):
    r, Session = repo
    _make_boat(Session, name="Real Boat")
    _make_boat(Session, name="Guest Boat", is_guest=True, guest_created_by=uuid.uuid4())

    result = r.list(include_guest=True)

    assert {b.name for b in result} == {"Real Boat", "Guest Boat"}


def test_list_claimable_returns_only_guest_boats_matching_query(repo):
    r, Session = repo
    _make_boat(Session, name="Real Aria")
    guest_id = _make_boat(Session, name="Guest Aria", is_guest=True,
                          guest_created_by=uuid.uuid4())
    _make_boat(Session, name="Guest Brezza", is_guest=True, guest_created_by=uuid.uuid4())

    result = r.list_claimable(q="Aria", limit=20)

    assert [b.id for b in result] == [guest_id]


# --- update() cannot flip is_guest (regression: PATCH /boats/{id}) ---------

def test_update_ignores_is_guest_and_guest_created_by(repo):
    """``BoatWriteModel.is_guest`` is honoured on create only; the repo's
    update path deliberately excludes both guest columns from
    ``_UPDATABLE_FIELDS`` so a plain boat edit can never promote a
    placeholder — only an approved claim (``clear_guest``) may."""
    r, Session = repo
    creator = uuid.uuid4()
    boat_id = _make_boat(Session, name="Guest Boat", is_guest=True, guest_created_by=creator)

    updated = r.update(boat_id, {
        "name": "Renamed Boat", "is_guest": False, "guest_created_by": uuid.uuid4(),
    })

    assert updated.name == "Renamed Boat"
    assert updated.is_guest is True
    assert updated.guest_created_by == creator


def test_clear_guest_clears_both_flags(repo):
    r, Session = repo
    boat_id = _make_boat(Session, is_guest=True, guest_created_by=uuid.uuid4())

    assert r.clear_guest(boat_id) is True

    boat = r.get(boat_id)
    assert boat.is_guest is False
    assert boat.guest_created_by is None


def test_clear_guest_on_unknown_boat_returns_false(repo):
    r, _ = repo
    assert r.clear_guest(uuid.uuid4()) is False


# --- claim creation / lookup -------------------------------------------------

def test_create_claim_returns_none_on_duplicate_pending(repo):
    """The partial unique index is on (boat_id, user_id) WHERE status =
    'pending' — a second pending claim from the same person on the same boat
    must be refused, not silently duplicated."""
    r, Session = repo
    boat_id = _make_boat(Session, is_guest=True)
    claimant = uuid.uuid4()
    first = r.create_claim(boat_id, user_id=claimant)

    assert first is not None
    second = r.create_claim(boat_id, user_id=claimant)
    assert second is None
    assert len(r.list_claims_for_boat(boat_id)) == 1


def test_create_claim_allowed_again_after_rejection(repo):
    """Regression test for the reason the unique index is partial rather than
    plain: a rejected claim must not permanently block the same person from
    trying again."""
    r, Session = repo
    boat_id = _make_boat(Session, is_guest=True)
    claimant = uuid.uuid4()
    first = r.create_claim(boat_id, user_id=claimant)
    assert r.resolve_claim(first.id, status="rejected", resolved_by=uuid.uuid4()) is True

    second = r.create_claim(boat_id, user_id=claimant)

    assert second is not None
    assert second.id != first.id
    assert second.status == "pending"


def test_get_claim_roundtrip(repo):
    r, Session = repo
    boat_id = _make_boat(Session, is_guest=True)
    claim = r.create_claim(boat_id, user_id=uuid.uuid4())

    assert r.get_claim(claim.id).id == claim.id
    assert r.get_claim(uuid.uuid4()) is None


def test_list_claims_for_boat_is_boat_scoped(repo):
    r, Session = repo
    boat_a = _make_boat(Session, is_guest=True)
    boat_b = _make_boat(Session, is_guest=True)
    claim_a = r.create_claim(boat_a, user_id=uuid.uuid4())
    r.create_claim(boat_b, user_id=uuid.uuid4())

    result = r.list_claims_for_boat(boat_a)

    assert [c.id for c in result] == [claim_a.id]


def test_list_claims_for_boat_filters_by_status(repo):
    r, Session = repo
    boat_id = _make_boat(Session, is_guest=True)
    pending = r.create_claim(boat_id, user_id=uuid.uuid4())
    rejected = r.create_claim(boat_id, user_id=uuid.uuid4())
    r.resolve_claim(rejected.id, status="rejected", resolved_by=uuid.uuid4())

    assert [c.id for c in r.list_claims_for_boat(boat_id, status="pending")] == [pending.id]
    assert [c.id for c in r.list_claims_for_boat(boat_id, status="rejected")] == [rejected.id]


def test_list_claims_by_user_is_user_scoped(repo):
    r, Session = repo
    boat_id = _make_boat(Session, is_guest=True)
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    my_claim = r.create_claim(boat_id, user_id=mine)
    r.create_claim(boat_id, user_id=theirs)

    result = r.list_claims_by_user(mine)

    assert [c.id for c in result] == [my_claim.id]


# --- resolving a claim: idempotency ------------------------------------------

def test_resolve_claim_succeeds_once(repo):
    r, Session = repo
    boat_id = _make_boat(Session, is_guest=True)
    claim = r.create_claim(boat_id, user_id=uuid.uuid4())
    approver = uuid.uuid4()

    assert r.resolve_claim(claim.id, status="approved", resolved_by=approver) is True

    resolved = r.get_claim(claim.id)
    assert resolved.status == "approved"
    assert resolved.resolved_by == approver
    assert resolved.resolved_at is not None


def test_resolve_claim_returns_false_when_already_resolved(repo):
    """A claim cannot be approved twice: the second call must not re-run
    whatever the first approval triggered (promote/merge)."""
    r, Session = repo
    boat_id = _make_boat(Session, is_guest=True)
    claim = r.create_claim(boat_id, user_id=uuid.uuid4())
    assert r.resolve_claim(claim.id, status="approved", resolved_by=uuid.uuid4()) is True

    second = r.resolve_claim(claim.id, status="approved", resolved_by=uuid.uuid4())

    assert second is False
    assert r.get_claim(claim.id).status == "approved"  # unchanged, not re-resolved


def test_resolve_claim_returns_false_for_unknown_claim(repo):
    r, _ = repo
    assert r.resolve_claim(uuid.uuid4(), status="approved", resolved_by=uuid.uuid4()) is False


# --- merge_into ---------------------------------------------------------------

def test_merge_into_moves_sessions_and_deletes_source(repo):
    r, Session = repo
    source_id = _make_boat(Session, name="Guest Boat", is_guest=True)
    target_id = _make_boat(Session, name="Real Boat")
    session_id = _make_session(Session, boat_id=source_id)

    moved = r.merge_into(source_id, target_id)

    assert moved.get("sessions") == 1
    with Session() as s:
        assert s.get(SessionORM, session_id).boat_id == target_id
    assert r.get(source_id) is None


def test_merge_into_keeps_higher_role_and_drops_duplicate_membership(repo):
    """A user who is a member of both boats must end up on exactly one
    ``user_boats`` row, keeping whichever role outranks the other."""
    r, Session = repo
    source_id = _make_boat(Session, is_guest=True)
    target_id = _make_boat(Session)
    shared_user = uuid.uuid4()
    r.add_member(source_id, user_id=shared_user, role="owner")
    r.add_member(target_id, user_id=shared_user, role="visitor")
    only_on_source = uuid.uuid4()
    r.add_member(source_id, user_id=only_on_source, role="admin")

    r.merge_into(source_id, target_id)

    with Session() as s:
        rows = s.query(UserBoatORM).filter(UserBoatORM.boat_id == target_id).all()
    by_user = {row.user_id: row.role for row in rows}
    assert by_user[shared_user] == "owner"  # higher of owner/visitor wins
    assert by_user[only_on_source] == "admin"  # moved over untouched
    assert len(rows) == 2  # no duplicate row for shared_user


def test_merge_into_raises_when_target_missing(repo):
    r, Session = repo
    source_id = _make_boat(Session, is_guest=True)

    with pytest.raises(ValueError, match="Boat not found"):
        r.merge_into(source_id, uuid.uuid4())
