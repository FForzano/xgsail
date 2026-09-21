"""Session crew repository behaviour added for the "was I aboard" filter and
editable crew role (``backend/repositories/sql/session_repo.py``).

Database-free, following ``test_session_detach.py``: in-memory SQLite, real
``SqlSessionRepo``. Router-level authorization for
``PATCH /sessions/{id}/crew/{user_id}`` is NOT covered here — this suite has
no ``TestClient`` (see ``test_live_recordings.py``'s note for the same
limitation on ``routers/live_recordings.py``) — so the auth matrix
(self-edit allowed; boat owner/admin or activity creator allowed via
``_can_edit``; anyone else 403) is exercised by hand / left for a future
TestClient-based suite. It mirrors ``DELETE /sessions/{id}/crew/{user_id}``'s
existing matrix exactly (same ``user.id != user_id and not _can_edit(...)``
condition), which is unit-tested nowhere else either.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import BoatORM, SessionCrewORM, SessionORM, UserBoatORM
from backend.repositories.sql.session_repo import SqlSessionRepo

T0 = datetime(2026, 1, 1, 10, 0, 0)


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        BoatORM.__table__,
        UserBoatORM.__table__,
        SessionORM.__table__,
        SessionCrewORM.__table__,
    ])
    Session = sessionmaker(bind=engine, future=True)
    return SqlSessionRepo(Session), Session


@pytest.fixture
def boat_id(repo):
    _, Session = repo
    with Session() as s:
        boat = BoatORM(name="Test Boat")
        s.add(boat)
        s.commit()
        return boat.id


def _make_session(Session, *, boat_id, started_at=T0):
    with Session() as s:
        row = SessionORM(activity_id=uuid.uuid4(), boat_id=boat_id, status="pending",
                         started_at=started_at)
        s.add(row)
        s.commit()
        return row.id


def _add_member(Session, *, boat_id, user_id, role="visitor"):
    with Session() as s:
        s.add(UserBoatORM(boat_id=boat_id, user_id=user_id, role=role))
        s.commit()


# --- set_crew_role -----------------------------------------------------------

def test_set_crew_role_changes_an_existing_row(repo, boat_id):
    session_repo, Session = repo
    session_id = _make_session(Session, boat_id=boat_id)
    user_id = uuid.uuid4()
    assert session_repo.add_crew(session_id, user_id=user_id, sailing_role="crew")

    result = session_repo.set_crew_role(session_id, user_id, sailing_role="skipper")

    assert result is True
    [row] = session_repo.list_crew(session_id)
    assert row.sailing_role == "skipper"


def test_set_crew_role_on_a_missing_row_returns_false(repo, boat_id):
    session_repo, Session = repo
    session_id = _make_session(Session, boat_id=boat_id)

    result = session_repo.set_crew_role(session_id, uuid.uuid4(), sailing_role="skipper")

    assert result is False
    assert session_repo.list_crew(session_id) == []


def test_set_crew_role_is_scoped_to_the_right_session(repo, boat_id):
    """A row for the same user on a different session must not be touched."""
    session_repo, Session = repo
    session_a = _make_session(Session, boat_id=boat_id)
    session_b = _make_session(Session, boat_id=boat_id)
    user_id = uuid.uuid4()
    session_repo.add_crew(session_a, user_id=user_id, sailing_role="crew")
    session_repo.add_crew(session_b, user_id=user_id, sailing_role="crew")

    session_repo.set_crew_role(session_a, user_id, sailing_role="skipper")

    assert session_repo.list_crew(session_a)[0].sailing_role == "skipper"
    assert session_repo.list_crew(session_b)[0].sailing_role == "crew"


# --- crew_session_ids ----------------------------------------------------------

def test_crew_session_ids_returns_only_sessions_the_user_crews(repo, boat_id):
    session_repo, Session = repo
    crewed = _make_session(Session, boat_id=boat_id)
    not_crewed = _make_session(Session, boat_id=boat_id)
    user_id = uuid.uuid4()
    session_repo.add_crew(crewed, user_id=user_id, sailing_role="crew")
    # Someone else crews the other session — must not leak in.
    session_repo.add_crew(not_crewed, user_id=uuid.uuid4(), sailing_role="crew")

    result = session_repo.crew_session_ids(user_id, [crewed, not_crewed])

    assert result == {crewed}


def test_crew_session_ids_empty_input_short_circuits(repo, boat_id):
    session_repo, _Session = repo
    assert session_repo.crew_session_ids(uuid.uuid4(), []) == set()


# --- list_for_user(aboard=...) ------------------------------------------------

def test_aboard_true_returns_only_crewed_sessions(repo, boat_id):
    session_repo, Session = repo
    user_id = uuid.uuid4()
    crewed = _make_session(Session, boat_id=boat_id)
    session_repo.add_crew(crewed, user_id=user_id, sailing_role="crew")
    # Visible via boat membership only, not crewed.
    member_only = _make_session(Session, boat_id=boat_id)
    _add_member(Session, boat_id=boat_id, user_id=user_id)

    result = session_repo.list_for_user(user_id, aboard=True)

    assert [s.id for s in result] == [crewed]


def test_aboard_false_returns_only_boat_member_sessions_not_crewed(repo, boat_id):
    session_repo, Session = repo
    user_id = uuid.uuid4()
    crewed = _make_session(Session, boat_id=boat_id)
    session_repo.add_crew(crewed, user_id=user_id, sailing_role="crew")
    member_only = _make_session(Session, boat_id=boat_id)
    _add_member(Session, boat_id=boat_id, user_id=user_id)

    result = session_repo.list_for_user(user_id, aboard=False)

    assert [s.id for s in result] == [member_only]


def test_aboard_unset_returns_the_full_union(repo, boat_id):
    session_repo, Session = repo
    user_id = uuid.uuid4()
    crewed = _make_session(Session, boat_id=boat_id)
    session_repo.add_crew(crewed, user_id=user_id, sailing_role="crew")
    member_only = _make_session(Session, boat_id=boat_id)
    _add_member(Session, boat_id=boat_id, user_id=user_id)

    result = {s.id for s in session_repo.list_for_user(user_id)}

    # Both the crewed session and the member-visible one are included;
    # aboard=None (default) is unfiltered, matching current behaviour.
    assert {crewed, member_only} <= result
