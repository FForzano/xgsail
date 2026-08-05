"""Regression tests for the boat configuration notebook (``boat_notes``)
repository methods in ``backend/repositories/sql/boat_repo.py``.

Follows the precedent in ``test_upcoming_feed.py``: this suite is
database-free, so we build an in-memory SQLite engine and create only the
tables under test (``boats`` + ``boat_notes``), then exercise the real
``SqlBoatRepo`` against it. ``UUIDPKMixin`` supplies a Python-side ``uuid4``
default, so the Postgres-only ``gen_random_uuid()`` server default is never
evaluated.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import BoatNoteORM, BoatORM, UserBoatORM
from backend.repositories.sql.boat_repo import SqlBoatRepo


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    # BoatORM.members is lazy="selectin", so any BoatORM query eagerly hits
    # user_boats even though these tests never touch membership — it must
    # exist too, or SQLite errors with "no such table: user_boats".
    Base.metadata.create_all(
        engine, tables=[BoatORM.__table__, BoatNoteORM.__table__, UserBoatORM.__table__]
    )
    Session = sessionmaker(bind=engine, future=True)
    return SqlBoatRepo(Session), Session


@pytest.fixture
def boat_id(repo):
    _, Session = repo
    with Session() as s:
        boat = BoatORM(name="Test Boat")
        s.add(boat)
        s.commit()
        return boat.id


@pytest.fixture
def other_boat_id(repo):
    _, Session = repo
    with Session() as s:
        boat = BoatORM(name="Other Boat")
        s.add(boat)
        s.commit()
        return boat.id


def _positions(notes):
    return [n.position for n in notes]


def test_list_notes_ordered_by_position(repo, boat_id):
    """Notes must come back ordered by ``position``, not insertion order.

    Inserted in the order third/first/second, then their ``position``
    values are forced out of insertion order directly (bypassing
    ``add_note``'s always-appends behaviour) so the assertion is
    deterministic rather than depending on ``created_at`` resolution.
    """
    r, Session = repo
    third = r.add_note(boat_id, "Third", "body-3")
    first = r.add_note(boat_id, "First", "body-1")
    second = r.add_note(boat_id, "Second", "body-2")

    with Session() as s:
        s.get(BoatNoteORM, first.id).position = 0
        s.get(BoatNoteORM, second.id).position = 1
        s.get(BoatNoteORM, third.id).position = 2
        s.commit()

    result = r.list_notes(boat_id)
    assert [n.id for n in result] == [first.id, second.id, third.id]
    assert _positions(result) == [0, 1, 2]


def test_add_note_positions_append_never_collide(repo, boat_id):
    r, _ = repo
    n1 = r.add_note(boat_id, "One", "b1")
    assert n1.position == 0
    n2 = r.add_note(boat_id, "Two", "b2")
    assert n2.position == 1
    n3 = r.add_note(boat_id, "Three", "b3")
    assert n3.position == 2


def test_reorder_notes_full_permutation_succeeds(repo, boat_id):
    r, _ = repo
    n1 = r.add_note(boat_id, "One", "b1")
    n2 = r.add_note(boat_id, "Two", "b2")
    n3 = r.add_note(boat_id, "Three", "b3")

    ok = r.reorder_notes(boat_id, [n3.id, n1.id, n2.id])
    assert ok is True

    result = r.list_notes(boat_id)
    assert [n.id for n in result] == [n3.id, n1.id, n2.id]
    assert _positions(result) == [0, 1, 2]


def test_reorder_notes_missing_id_fails_and_leaves_positions(repo, boat_id):
    r, _ = repo
    n1 = r.add_note(boat_id, "One", "b1")
    n2 = r.add_note(boat_id, "Two", "b2")
    n3 = r.add_note(boat_id, "Three", "b3")
    before = _positions(r.list_notes(boat_id))

    ok = r.reorder_notes(boat_id, [n1.id, n2.id])  # missing n3
    assert ok is False
    assert _positions(r.list_notes(boat_id)) == before


def test_reorder_notes_extra_unknown_id_fails_and_leaves_positions(repo, boat_id):
    r, _ = repo
    n1 = r.add_note(boat_id, "One", "b1")
    n2 = r.add_note(boat_id, "Two", "b2")
    before = _positions(r.list_notes(boat_id))
    unknown_id = uuid.uuid4()

    ok = r.reorder_notes(boat_id, [n1.id, n2.id, unknown_id])
    assert ok is False
    assert _positions(r.list_notes(boat_id)) == before


def test_reorder_notes_duplicated_id_fails_and_leaves_positions(repo, boat_id):
    r, _ = repo
    n1 = r.add_note(boat_id, "One", "b1")
    n2 = r.add_note(boat_id, "Two", "b2")
    before = _positions(r.list_notes(boat_id))

    ok = r.reorder_notes(boat_id, [n1.id, n1.id])  # n2 missing, n1 duplicated
    assert ok is False
    assert _positions(r.list_notes(boat_id)) == before


def test_reorder_notes_id_from_other_boat_fails_and_leaves_positions(
    repo, boat_id, other_boat_id
):
    r, _ = repo
    n1 = r.add_note(boat_id, "One", "b1")
    n2 = r.add_note(boat_id, "Two", "b2")
    foreign = r.add_note(other_boat_id, "Foreign", "bf")
    before = _positions(r.list_notes(boat_id))

    ok = r.reorder_notes(boat_id, [n1.id, foreign.id])  # n2 missing, foreign wrong boat
    assert ok is False
    assert _positions(r.list_notes(boat_id)) == before
    # the other boat's note is untouched too
    assert r.get_note(other_boat_id, foreign.id).position == 0


def test_update_note_changes_title_and_body_only(repo, boat_id, other_boat_id):
    r, _ = repo
    note = r.add_note(boat_id, "Original", "orig-body")
    original_position = note.position

    updated = r.update_note(
        note.id,
        {"title": "New Title", "body": "New body", "position": 99, "boat_id": other_boat_id},
    )

    assert updated.title == "New Title"
    assert updated.body == "New body"
    assert updated.position == original_position
    assert updated.boat_id == boat_id


def test_list_notes_is_boat_scoped(repo, boat_id, other_boat_id):
    r, _ = repo
    mine = r.add_note(boat_id, "Mine", "b")
    r.add_note(other_boat_id, "Theirs", "b")

    result = r.list_notes(boat_id)
    assert [n.id for n in result] == [mine.id]


def test_get_note_cross_boat_returns_none(repo, boat_id, other_boat_id):
    r, _ = repo
    note = r.add_note(boat_id, "Mine", "b")

    assert r.get_note(other_boat_id, note.id) is None
    assert r.get_note(boat_id, note.id).id == note.id


def test_remove_note(repo, boat_id, other_boat_id):
    r, _ = repo
    note = r.add_note(boat_id, "Mine", "b")
    foreign = r.add_note(other_boat_id, "Theirs", "b")

    assert r.remove_note(boat_id, uuid.uuid4()) is False  # unknown id
    assert r.remove_note(boat_id, foreign.id) is False  # belongs to another boat
    assert r.get_note(other_boat_id, foreign.id) is not None  # untouched

    assert r.remove_note(boat_id, note.id) is True
    assert r.get_note(boat_id, note.id) is None
    assert r.list_notes(boat_id) == []
