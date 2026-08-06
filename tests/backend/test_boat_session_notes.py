"""Regression tests for the boat "logbook" view's backing repository method,
``SqlSessionRepo.list_with_notes_for_boat`` (``backend/repositories/sql/
session_repo.py``).

Follows the precedent in ``test_boat_notebook.py``/``test_upcoming_feed.py``:
database-free, in-memory SQLite, only the tables this query actually touches
or that SQLAlchemy's metadata needs to resolve.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import ActivityORM, BoatORM, SessionORM, SessionUploadORM, UserBoatORM
from backend.repositories.sql.session_repo import SqlSessionRepo
from backend.richtext import to_plain_text


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            SessionORM.__table__,
            ActivityORM.__table__,  # sessions.activity_id FK target (NOT NULL)
            BoatORM.__table__,  # sessions.boat_id FK target (NOT NULL)
            # sessions.primary_nav_upload_id FK target (use_alter=True, but
            # still needed for create_all to resolve the table's metadata).
            SessionUploadORM.__table__,
            # BoatORM.members is lazy="selectin", so any BoatORM-touching
            # query eagerly hits user_boats even though these tests never
            # touch membership — it must exist too, or SQLite errors with
            # "no such table: user_boats".
            UserBoatORM.__table__,
        ],
    )
    Session = sessionmaker(bind=engine, future=True)
    return SqlSessionRepo(Session), Session


@pytest.fixture
def activity_id(repo):
    _, Session = repo
    with Session() as s:
        activity = ActivityORM(type="training")
        s.add(activity)
        s.commit()
        return activity.id


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


def _dt(offset_days):
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=offset_days)


def _make_session(Session, *, activity_id, boat_id, notes=None, started_at=None):
    """Builds the ORM row directly (not through ``SqlSessionRepo.update``),
    so ``notes_plain`` is derived here exactly the way the repo's write path
    derives it — keeping these read-side tests decoupled from the mirroring
    logic, which is covered separately in the ``notes_plain mirroring``
    tests below."""
    with Session() as s:
        orm = SessionORM(
            activity_id=activity_id,
            boat_id=boat_id,
            notes=notes,
            notes_plain=to_plain_text(notes) if notes is not None else None,
            started_at=started_at,
        )
        s.add(orm)
        s.commit()
        return orm.id


def test_null_notes_excluded(repo, activity_id, boat_id):
    r, Session = repo
    _make_session(Session, activity_id=activity_id, boat_id=boat_id, notes=None)

    assert r.list_with_notes_for_boat(boat_id) == []


def test_empty_string_notes_excluded(repo, activity_id, boat_id):
    r, Session = repo
    _make_session(Session, activity_id=activity_id, boat_id=boat_id, notes="")

    assert r.list_with_notes_for_boat(boat_id) == []


def test_space_only_notes_excluded(repo, activity_id, boat_id):
    """The predicate is ``trim(notes) != ''``, not ``notes != ''`` — pure
    spaces must not count as a real note."""
    r, Session = repo
    _make_session(Session, activity_id=activity_id, boat_id=boat_id, notes="   ")

    assert r.list_with_notes_for_boat(boat_id) == []


def test_tab_and_newline_only_notes_excluded(repo, activity_id, boat_id):
    """Regression: one-arg trim()/btrim() strips spaces only, so a note of
    bare newlines used to survive the filter as a blank logbook row."""
    r, Session = repo
    _make_session(Session, activity_id=activity_id, boat_id=boat_id, notes="\n\t ")

    assert r.list_with_notes_for_boat(boat_id) == []


def test_real_note_included(repo, activity_id, boat_id):
    r, Session = repo
    session_id = _make_session(
        Session, activity_id=activity_id, boat_id=boat_id, notes="Choppy water, eased the vang."
    )

    result = r.list_with_notes_for_boat(boat_id)
    assert [s.id for s in result] == [session_id]


def test_ordered_newest_first_nulls_last(repo, activity_id, boat_id):
    """Newest ``started_at`` first; a session with no ``started_at`` at all
    sorts last, not first."""
    r, Session = repo
    oldest = _make_session(
        Session, activity_id=activity_id, boat_id=boat_id, notes="old", started_at=_dt(0)
    )
    newest = _make_session(
        Session, activity_id=activity_id, boat_id=boat_id, notes="new", started_at=_dt(2)
    )
    middle = _make_session(
        Session, activity_id=activity_id, boat_id=boat_id, notes="mid", started_at=_dt(1)
    )
    no_start = _make_session(
        Session, activity_id=activity_id, boat_id=boat_id, notes="no start", started_at=None
    )

    result = r.list_with_notes_for_boat(boat_id)
    assert [s.id for s in result] == [newest, middle, oldest, no_start]


def test_q_filters_case_insensitively_on_note_content(repo, activity_id, boat_id):
    r, Session = repo
    vang = _make_session(
        Session, activity_id=activity_id, boat_id=boat_id, notes="eased the VANG", started_at=_dt(1)
    )
    _make_session(
        Session, activity_id=activity_id, boat_id=boat_id, notes="trimmed the jib", started_at=_dt(0)
    )

    result = r.list_with_notes_for_boat(boat_id, q="vang")
    assert [s.id for s in result] == [vang]


def test_q_composes_with_limit_and_offset(repo, activity_id, boat_id):
    """``q`` narrows in SQL before ``limit``/``offset`` apply, so pagination
    walks only the matching rows — not a limited slice of everything."""
    r, Session = repo
    matches = [
        _make_session(
            Session, activity_id=activity_id, boat_id=boat_id, notes=f"reef #{i}", started_at=_dt(i)
        )
        for i in range(3)
    ]
    _make_session(Session, activity_id=activity_id, boat_id=boat_id, notes="calm day", started_at=_dt(3))

    page = r.list_with_notes_for_boat(boat_id, q="reef", limit=2, offset=1)
    assert [s.id for s in page] == [matches[1], matches[0]]


def test_boat_scoped(repo, activity_id, boat_id, other_boat_id):
    r, Session = repo
    mine = _make_session(
        Session, activity_id=activity_id, boat_id=boat_id, notes="mine", started_at=_dt(0)
    )
    _make_session(
        Session, activity_id=activity_id, boat_id=other_boat_id, notes="theirs", started_at=_dt(0)
    )

    result = r.list_with_notes_for_boat(boat_id)
    assert [s.id for s in result] == [mine]


def test_limit_and_offset_paginate_a_known_ordering(repo, activity_id, boat_id):
    r, Session = repo
    ids = [
        _make_session(
            Session, activity_id=activity_id, boat_id=boat_id, notes=f"note {i}", started_at=_dt(i)
        )
        for i in range(5)
    ]
    # Newest first: ids[4], ids[3], ids[2], ids[1], ids[0]
    expected_order = list(reversed(ids))

    first_page = r.list_with_notes_for_boat(boat_id, limit=2, offset=0)
    assert [s.id for s in first_page] == expected_order[0:2]

    second_page = r.list_with_notes_for_boat(boat_id, limit=2, offset=2)
    assert [s.id for s in second_page] == expected_order[2:4]

    last_page = r.list_with_notes_for_boat(boat_id, limit=2, offset=4)
    assert [s.id for s in last_page] == expected_order[4:5]


def test_html_note_stripped_of_empty_paragraph_excluded(repo, activity_id, boat_id):
    """``<p></p>`` is what an emptied rich-text note becomes post-sanitizing —
    not the empty string — so the blank filter must catch it via
    ``notes_plain``, not by inspecting the HTML in ``notes``."""
    r, Session = repo
    _make_session(Session, activity_id=activity_id, boat_id=boat_id, notes="<p></p>")

    assert r.list_with_notes_for_boat(boat_id) == []


def test_q_matches_text_split_across_html_tags(repo, activity_id, boat_id):
    """``q="vento forte"`` must find a note stored as
    ``vento <strong>forte</strong>`` — an ILIKE against raw ``notes`` would
    miss it because the tag sits between the two words."""
    r, Session = repo
    session_id = _make_session(
        Session, activity_id=activity_id, boat_id=boat_id,
        notes="<p>vento <strong>forte</strong> oggi</p>",
    )

    result = r.list_with_notes_for_boat(boat_id, q="vento forte")
    assert [s.id for s in result] == [session_id]


def test_q_does_not_match_html_tag_names(repo, activity_id, boat_id):
    """``q="strong"`` must not match a note whose HTML happens to use a
    ``<strong>`` tag — the search runs on the text a user would actually
    read, not on markup."""
    r, Session = repo
    _make_session(
        Session, activity_id=activity_id, boat_id=boat_id,
        notes="<p>vento <strong>forte</strong> oggi</p>",
    )

    assert r.list_with_notes_for_boat(boat_id, q="strong") == []


class TestNotesPlainMirroring:
    """``SqlSessionRepo.update``/``create`` are the only writers of ``notes``
    outside a migration, so they're the only place that can keep
    ``notes_plain`` in sync — this class covers that mirroring directly,
    independent of the read-side filtering covered above."""

    def test_update_derives_notes_plain_from_html(self, repo, activity_id, boat_id):
        r, Session = repo
        session_id = _make_session(Session, activity_id=activity_id, boat_id=boat_id)

        updated = r.update(session_id, {"notes": "<p>vento <strong>forte</strong></p>"})

        assert updated.notes_plain == "vento forte"

    def test_update_with_none_notes_sets_none_notes_plain(self, repo, activity_id, boat_id):
        r, Session = repo
        session_id = _make_session(Session, activity_id=activity_id, boat_id=boat_id, notes="<p>x</p>")

        updated = r.update(session_id, {"notes": None})

        assert updated.notes is None
        assert updated.notes_plain is None

    def test_update_without_notes_key_leaves_notes_plain_untouched(self, repo, activity_id, boat_id):
        """A partial update (``exclude_unset``) that never mentions ``notes``
        must not clobber the existing mirror — this is the case an
        unconditional ``to_plain_text(changes.get("notes"))`` would get
        wrong, turning every unrelated PATCH into a note-wipe."""
        r, Session = repo
        session_id = _make_session(Session, activity_id=activity_id, boat_id=boat_id, notes="<p>hello</p>")

        updated = r.update(session_id, {"status": "processed"})

        assert updated.notes_plain == "hello"

    def test_create_derives_notes_plain_from_html(self, repo, activity_id, boat_id):
        r, Session = repo

        session = r.create({
            "activity_id": activity_id,
            "boat_id": boat_id,
            "notes": "<p>eased the <em>vang</em></p>",
        })

        assert session.notes_plain == "eased the vang"

    def test_create_without_notes_leaves_notes_plain_none(self, repo, activity_id, boat_id):
        r, Session = repo

        session = r.create({"activity_id": activity_id, "boat_id": boat_id})

        assert session.notes_plain is None
