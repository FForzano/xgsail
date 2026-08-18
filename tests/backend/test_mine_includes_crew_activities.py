"""The personal diary's ``?mine=true`` filter
(``SqlActivityRepo.list(crewed_or_created_by=...)``).

When two people aboard both record an outing, the shared session lives in the
private ``solo`` activity of whoever uploaded first — so an authorship-only
filter hid the other person's own outing from their own diary. "Mine" has to
mean the outings that are mine to look back on, which includes the ones
somebody else started and I sailed.

Real sqlite session against the actual ORM/repo, same reasoning as
``test_upcoming_feed.py``: the change is a WHERE clause, and a hand-rolled
fake cannot exercise one.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import (
    ActivityORM,
    PermissionORM,
    RolePermissionORM,
    SessionCrewORM,
    SessionORM,
    SessionUploadORM,
    UserClubORM,
    UserGroupORM,
    UserRoleORM,
)
from backend.repositories.sql.activity_repo import SqlActivityRepo

ME = uuid.uuid4()
HELM = uuid.uuid4()
STRANGER = uuid.uuid4()
BOAT = uuid.uuid4()


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        ActivityORM.__table__,
        UserClubORM.__table__,
        UserGroupORM.__table__,
        SessionORM.__table__,
        # sessions.primary_nav_upload_id FK target (use_alter=True)
        SessionUploadORM.__table__,
        SessionCrewORM.__table__,
        # Reached by _visibility_clause's scoped-club.manage check.
        UserRoleORM.__table__,
        RolePermissionORM.__table__,
        PermissionORM.__table__,
    ])
    Session = sessionmaker(bind=engine, future=True)
    return SqlActivityRepo(Session), Session


def _at(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _activity(Session, *, created_by, crew=(), when=0) -> uuid.UUID:
    with Session() as s:
        activity = ActivityORM(type="solo", visibility="private",
                               created_by=created_by, started_at=_at(when))
        s.add(activity)
        s.commit()
        activity_id = activity.id
        if crew:
            session = SessionORM(activity_id=activity_id, boat_id=BOAT,
                                 started_at=_at(when))
            s.add(session)
            s.commit()
            for user_id in crew:
                s.add(SessionCrewORM(session_id=session.id, user_id=user_id,
                                     sailing_role="crew"))
            s.commit()
    return activity_id


def test_mine_includes_an_outing_i_only_sailed(repo):
    """The bow's phone merged into the helm's private solo activity: it is the
    bow's outing too, and it has to reach their diary."""
    activity_repo, Session = repo
    theirs = _activity(Session, created_by=HELM, crew=[HELM, ME], when=1)
    mine = _activity(Session, created_by=ME, when=2)

    found = activity_repo.list(crewed_or_created_by=ME, viewer_id=ME)

    assert {a.id for a in found} == {theirs, mine}


def test_mine_still_excludes_outings_i_had_no_part_in(repo):
    activity_repo, Session = repo
    _activity(Session, created_by=STRANGER, crew=[STRANGER], when=1)
    mine = _activity(Session, created_by=ME, when=2)

    found = activity_repo.list(crewed_or_created_by=ME, viewer_id=ME)

    assert [a.id for a in found] == [mine]


def test_an_activity_with_several_crewed_sessions_appears_once(repo):
    """An IN subquery rather than a join, so the caller's page-size
    arithmetic (``useDiaryFeed``'s ``getNextPageParam``) keeps working."""
    activity_repo, Session = repo
    activity_id = _activity(Session, created_by=HELM, crew=[ME], when=1)
    with Session() as s:
        second = SessionORM(activity_id=activity_id, boat_id=uuid.uuid4(),
                            started_at=_at(1))
        s.add(second)
        s.commit()
        s.add(SessionCrewORM(session_id=second.id, user_id=ME, sailing_role="crew"))
        s.commit()

    found = activity_repo.list(crewed_or_created_by=ME, viewer_id=ME)

    assert [a.id for a in found] == [activity_id]


def test_the_filter_runs_in_sql_not_after_the_page(repo):
    """Applied before LIMIT/OFFSET, for the reason ``_visibility_clause``
    spells out: filtering a returned page in Python makes pages come back
    short or empty."""
    activity_repo, Session = repo
    _activity(Session, created_by=STRANGER, crew=[STRANGER], when=1)
    _activity(Session, created_by=ME, when=2)
    _activity(Session, created_by=HELM, crew=[ME], when=3)

    page = activity_repo.list(crewed_or_created_by=ME, viewer_id=ME, limit=2)

    assert len(page) == 2
