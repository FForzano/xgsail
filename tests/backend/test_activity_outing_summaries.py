"""Per-activity summary of the viewer's own outing
(``SqlActivityRepo.outing_summaries`` + ``activity_payload(summaries=...)``).

Database-free, following ``test_session_activity_photos.py``: in-memory SQLite
with the real repository over the real ORM tables. ``backend.routers`` is
pre-seeded as a bare package so ``_common`` can be imported without pulling in
every router module (and their live AWS/Postgres clients).
"""

import importlib
import sys
import types
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import (
    ActivityORM,
    BoatORM,
    ImageORM,
    SessionCrewORM,
    SessionORM,
    SessionStatsORM,
    UserBoatORM,
    UserORM,
    UserRoleORM,
)
from backend.repositories.sql.activity_repo import OUTING_CREW_CAP, SqlActivityRepo


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            UserORM.__table__, UserRoleORM.__table__,  # selectin relationships
            BoatORM.__table__, UserBoatORM.__table__, ActivityORM.__table__,
            SessionORM.__table__, SessionCrewORM.__table__,
            SessionStatsORM.__table__, ImageORM.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, future=True)
    factory.engine = engine
    return factory


@pytest.fixture
def repo(db):
    return SqlActivityRepo(db)


def _user(db, name="Sailor", image_id=None):
    with db() as s:
        u = UserORM(email=f"{uuid.uuid4()}@example.test", first_name=name,
                    last_name="Test", terms_and_conditions=True,
                    profile_image_id=image_id)
        s.add(u)
        s.commit()
        return u.id


def _activity(db):
    with db() as s:
        a = ActivityORM(type="training")
        s.add(a)
        s.commit()
        return a.id


def _session(db, activity_id, boat_id, crew, stats=None):
    with db() as s:
        sess = SessionORM(activity_id=activity_id, boat_id=boat_id)
        s.add(sess)
        s.flush()
        for user_id in crew:
            s.add(SessionCrewORM(session_id=sess.id, user_id=user_id))
        if stats is not None:
            s.add(SessionStatsORM(session_id=sess.id, **stats))
        s.commit()
        return sess.id


@pytest.fixture
def boat(db):
    with db() as s:
        b = BoatORM(name="Aria", sail_number="ITA 1")
        s.add(b)
        s.commit()
        return b.id


def test_sums_and_max_over_viewer_sessions_only(repo, db, boat):
    me, friend, stranger = _user(db, "Me"), _user(db, "Friend"), _user(db, "Stranger")
    act = _activity(db)
    _session(db, act, boat, [me, friend],
             dict(distance_m=1000.0, duration_s=600, max_speed_kts=5.0))
    _session(db, act, boat, [me],
             dict(distance_m=500.0, duration_s=300, max_speed_kts=8.5))
    _session(db, act, boat, [stranger],
             dict(distance_m=9999.0, duration_s=9999, max_speed_kts=40.0))

    summary = repo.outing_summaries([act], me)[act]

    assert summary["session_count"] == 2
    assert summary["distance_m"] == 1500.0
    assert summary["duration_s"] == 900
    assert summary["max_speed_kts"] == 8.5
    assert [c["id"] for c in summary["crew"]] == [friend]


def test_crew_excludes_viewer_dedupes_and_has_no_email(repo, db, boat):
    me, friend = _user(db, "Me"), _user(db, "Friend")
    act = _activity(db)
    _session(db, act, boat, [me, friend])
    _session(db, act, boat, [friend, me])

    crew = repo.outing_summaries([act], me)[act]["crew"]

    assert [c["id"] for c in crew] == [friend]
    assert set(crew[0]) == {"id", "first_name", "last_name", "profile_image"}


def test_crew_is_capped(repo, db, boat):
    me = _user(db)
    act = _activity(db)
    _session(db, act, boat, [me] + [_user(db) for _ in range(OUTING_CREW_CAP + 3)])

    assert len(repo.outing_summaries([act], me)[act]["crew"]) == OUTING_CREW_CAP


def test_activity_without_viewer_is_absent(repo, db, boat):
    me, other = _user(db), _user(db)
    act = _activity(db)
    _session(db, act, boat, [other], dict(distance_m=1.0))

    assert repo.outing_summaries([act], me) == {}


def test_null_or_missing_stats_are_none_not_zero(repo, db, boat):
    me = _user(db)
    act = _activity(db)
    _session(db, act, boat, [me])  # no stats row
    _session(db, act, boat, [me], dict(distance_m=None, duration_s=None))

    summary = repo.outing_summaries([act], me)[act]

    assert summary["session_count"] == 2
    assert summary["distance_m"] is None
    assert summary["duration_s"] is None
    assert summary["max_speed_kts"] is None


def test_empty_ids_returns_empty(repo):
    assert repo.outing_summaries([], uuid.uuid4()) == {}


def test_query_count_is_constant_across_activities(repo, db, boat):
    me, friend = _user(db), _user(db)
    acts = [_activity(db) for _ in range(5)]
    for act in acts:
        _session(db, act, boat, [me, friend], dict(distance_m=1.0))
    statements = []
    event.listen(db.engine, "before_cursor_execute",
                 lambda *a: statements.append(a[2]))

    result = repo.outing_summaries(acts, me)

    assert len(result) == 5
    assert len(statements) == 2


def test_profile_image_is_returned_and_deleted_image_dropped(repo, db, boat):
    with db() as s:
        ok = ImageORM(created_by=None, ref="media/ok", status="processed")
        gone = ImageORM(created_by=None, ref="media/gone", status="deleted")
        s.add_all([ok, gone])
        s.commit()
        ok_id, gone_id = ok.id, gone.id
    me = _user(db, "Me")
    with_img = _user(db, "A", image_id=ok_id)
    deleted_img = _user(db, "B", image_id=gone_id)
    act = _activity(db)
    _session(db, act, boat, [me, with_img, deleted_img])

    by_id = {c["id"]: c for c in repo.outing_summaries([act], me)[act]["crew"]}

    assert by_id[with_img]["profile_image"].id == ok_id
    assert by_id[deleted_img]["profile_image"] is None


@pytest.fixture
def common(monkeypatch):
    pkg = types.ModuleType("backend.routers")
    pkg.__path__ = [str(Path(__file__).resolve().parents[2] / "backend" / "routers")]
    monkeypatch.setitem(sys.modules, "backend.routers", pkg)
    monkeypatch.delitem(sys.modules, "backend.routers._common", raising=False)
    # _common calls get_repos() at import, which would run migrations on Postgres.
    monkeypatch.setattr("backend.repositories.get_repos", lambda: types.SimpleNamespace())
    return importlib.import_module("backend.routers._common")


class _FakeActivity:
    id = uuid.uuid4()
    thumbnail_image_id = None

    def to_dict(self):
        return {"id": self.id}


def test_activity_payload_adds_summary_only_when_passed(common, monkeypatch):
    monkeypatch.setattr(common.media, "image_payload", lambda _id: None)
    covers = {}
    activity = _FakeActivity()
    image = types.SimpleNamespace(id=uuid.uuid4(), ref="media/x")
    monkeypatch.setattr(common.media, "get_blob_store",
                        lambda: types.SimpleNamespace(download_ref=lambda r: f"https://b/{r}"))
    summary = {"session_count": 1, "distance_m": 10.0, "duration_s": 5,
               "max_speed_kts": 3.0,
               "crew": [{"id": uuid.uuid4(), "first_name": "A", "last_name": "B",
                         "profile_image": image}]}

    assert "summary" not in common.activity_payload(activity, covers=covers)
    assert common.activity_payload(activity, covers=covers, summaries={})["summary"] is None
    shaped = common.activity_payload(
        activity, covers=covers, summaries={activity.id: summary})["summary"]
    assert shaped["crew"][0]["profile_image"] == {
        "image_id": image.id, "url": "https://b/media/x"}
    assert shaped["distance_m"] == 10.0
