"""Regression tests for the people-search repository methods in
``backend/repositories/sql/user_repo.py``: ``SqlUserRepo.search`` and
``SqlUserRepo.related_user_ids``. Privacy-adjacent — these control who a
user can discover/be discovered by, so both get explicit coverage per the
testing policy.

Follows the precedent in ``test_boat_notebook.py``/``test_boat_session_notes.py``:
database-free, in-memory SQLite, create only the tables under test.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import UserClubORM, UserGroupORM, UserBoatORM, UserORM, UserRoleORM
from backend.repositories.sql.user_repo import SqlUserRepo


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            UserORM.__table__,
            # UserORM.roles is lazy="selectin", so any UserORM query eagerly
            # hits user_roles even though these tests never touch RBAC — it
            # must exist too, or SQLite errors with "no such table: user_roles".
            UserRoleORM.__table__,
            UserClubORM.__table__,
            UserGroupORM.__table__,
            UserBoatORM.__table__,
        ],
    )
    Session = sessionmaker(bind=engine, future=True)
    return SqlUserRepo(Session), Session


def _make_user(Session, *, first_name=None, last_name=None, email=None,
                is_active=True, deleted_at=None):
    email = email or f"{uuid.uuid4()}@example.com"
    with Session() as s:
        orm = UserORM(
            email=email,
            password_hash="x",
            first_name=first_name,
            last_name=last_name,
            is_active=is_active,
            deleted_at=deleted_at,
        )
        s.add(orm)
        s.commit()
        return orm.id


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_matches_first_name_case_insensitively(repo):
    r, Session = repo
    mario_id = _make_user(Session, first_name="Mario", last_name="Bianchi")

    assert [u.id for u in r.search("mar")] == [mario_id]
    assert [u.id for u in r.search("MAR")] == [mario_id]


def test_search_matches_last_name(repo):
    r, Session = repo
    user_id = _make_user(Session, first_name="Luca", last_name="Verdi")

    assert [u.id for u in r.search("verdi")] == [user_id]


def test_search_matches_email(repo):
    r, Session = repo
    user_id = _make_user(Session, first_name="Anna", last_name="Neri",
                          email="anna.neri@example.com")

    assert [u.id for u in r.search("anna.neri")] == [user_id]


def test_search_matches_full_name_across_columns(repo):
    """The concatenation branch: neither column alone contains "mario
    rossi", only first_name + " " + last_name does."""
    r, Session = repo
    user_id = _make_user(Session, first_name="Mario", last_name="Rossi")

    result = r.search("mario rossi")
    assert [u.id for u in result] == [user_id]


def test_search_is_substring_not_prefix_only(repo):
    r, Session = repo
    user_id = _make_user(Session, first_name="Giulia", last_name="Rossi")

    assert [u.id for u in r.search("ossi")] == [user_id]


def test_search_excludes_inactive_users(repo):
    r, Session = repo
    _make_user(Session, first_name="Mario", last_name="Rossi", is_active=False)

    assert r.search("mario") == []


def test_search_excludes_soft_deleted_users(repo):
    from datetime import datetime, timezone

    r, Session = repo
    _make_user(Session, first_name="Mario", last_name="Rossi",
               deleted_at=datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert r.search("mario") == []


def test_search_orders_by_last_name_then_first_name(repo):
    r, Session = repo
    b_first = _make_user(Session, first_name="Bruno", last_name="Alfa")
    a_second = _make_user(Session, first_name="Anna", last_name="Beta")
    a_first = _make_user(Session, first_name="Aldo", last_name="Beta")

    result = r.search("a")
    assert [u.id for u in result] == [b_first, a_first, a_second]


def test_search_limit_caps_results(repo):
    r, Session = repo
    for i in range(5):
        _make_user(Session, first_name=f"Marco{i}", last_name="Test")

    result = r.search("marco", limit=2)
    assert len(result) == 2


def test_search_no_match_returns_empty_list(repo):
    r, Session = repo
    _make_user(Session, first_name="Mario", last_name="Rossi")

    assert r.search("zzzznomatch") == []


# ---------------------------------------------------------------------------
# related_user_ids
# ---------------------------------------------------------------------------


def _add_club_membership(Session, user_id, club_id):
    with Session() as s:
        s.add(UserClubORM(user_id=user_id, club_id=club_id, status="active"))
        s.commit()


def _add_group_membership(Session, user_id, group_id):
    with Session() as s:
        s.add(UserGroupORM(user_id=user_id, group_id=group_id, role="member"))
        s.commit()


def _add_boat_membership(Session, user_id, boat_id):
    with Session() as s:
        s.add(UserBoatORM(user_id=user_id, boat_id=boat_id, role="visitor"))
        s.commit()


def test_related_user_ids_shares_club(repo):
    r, Session = repo
    me = _make_user(Session, first_name="Me")
    other = _make_user(Session, first_name="Other")
    club_id = uuid.uuid4()
    _add_club_membership(Session, me, club_id)
    _add_club_membership(Session, other, club_id)

    assert r.related_user_ids(me) == {other}


def test_related_user_ids_shares_group(repo):
    r, Session = repo
    me = _make_user(Session, first_name="Me")
    other = _make_user(Session, first_name="Other")
    group_id = uuid.uuid4()
    _add_group_membership(Session, me, group_id)
    _add_group_membership(Session, other, group_id)

    assert r.related_user_ids(me) == {other}


def test_related_user_ids_shares_boat(repo):
    r, Session = repo
    me = _make_user(Session, first_name="Me")
    other = _make_user(Session, first_name="Other")
    boat_id = uuid.uuid4()
    _add_boat_membership(Session, me, boat_id)
    _add_boat_membership(Session, other, boat_id)

    assert r.related_user_ids(me) == {other}


def test_related_user_ids_never_includes_caller(repo):
    r, Session = repo
    me = _make_user(Session, first_name="Me")
    club_id = uuid.uuid4()
    group_id = uuid.uuid4()
    boat_id = uuid.uuid4()
    _add_club_membership(Session, me, club_id)
    _add_group_membership(Session, me, group_id)
    _add_boat_membership(Session, me, boat_id)

    assert me not in r.related_user_ids(me)


def test_related_user_ids_excludes_unrelated_user(repo):
    r, Session = repo
    me = _make_user(Session, first_name="Me")
    stranger = _make_user(Session, first_name="Stranger")
    club_id = uuid.uuid4()
    _add_club_membership(Session, me, club_id)
    # stranger shares nothing with me

    assert stranger not in r.related_user_ids(me)


def test_related_user_ids_no_memberships_returns_empty_set(repo):
    r, Session = repo
    me = _make_user(Session, first_name="Lonely")

    assert r.related_user_ids(me) == set()


def test_related_user_ids_deduplicates_across_club_and_boat(repo):
    """A person sharing both a club AND a boat with the caller must appear
    once — related_user_ids returns a set, not a multiset."""
    r, Session = repo
    me = _make_user(Session, first_name="Me")
    other = _make_user(Session, first_name="Other")
    club_id = uuid.uuid4()
    boat_id = uuid.uuid4()
    _add_club_membership(Session, me, club_id)
    _add_club_membership(Session, other, club_id)
    _add_boat_membership(Session, me, boat_id)
    _add_boat_membership(Session, other, boat_id)

    result = r.related_user_ids(me)
    assert result == {other}
