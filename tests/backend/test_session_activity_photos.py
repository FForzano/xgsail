"""Attributed session/activity photo galleries
(``backend/services/media.py``, ``backend/repositories/sql/session_repo.py``,
``backend/repositories/sql/activity_repo.py``, ``backend/routers/sessions.py``,
``backend/routers/activities.py``).

Database-free, following ``test_boat_session_notes.py``: an in-memory SQLite
engine with the real repositories over the real ORM tables, plus a fake
``get_repos()``/``get_blob_store()`` for the service-layer helpers.

``media.session_photo_payload`` does ``from ..routers._common import
user_summary`` as a local import (the established pattern in
``services/physio.py``/``nav_source.py`` — "avoids an import cycle"). Actually
importing ``backend.routers._common`` for real pulls in every router module
and, through them, a live AWS/Postgres client at import time (see
``test_admin_access_log.py``'s comment) — infeasible in this suite. So these
tests pre-seed ``sys.modules`` with a tiny fake ``backend.routers``/
``backend.routers._common`` before exercising anything that triggers that
import, exactly the way a real ``user_summary`` would answer for the users
seeded in the fixture DB below.
"""

import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import (
    ActivityORM,
    BoatORM,
    ImageORM,
    SessionCrewORM,
    SessionORM,
    SessionPhotoORM,
    SessionUploadORM,
    UserBoatORM,
    UserORM,
    UserRoleORM,
)
from backend.repositories.sql.activity_repo import SqlActivityRepo
from backend.repositories.sql.boat_repo import SqlBoatRepo
from backend.repositories.sql.media_repo import SqlMediaRepo
from backend.repositories.sql.session_repo import SqlSessionRepo
from backend.repositories.sql.user_repo import SqlUserRepo


class _FakeBlobStore:
    """``download_ref`` just needs to be deterministic — no network."""

    def download_ref(self, ref, expiry=3600):
        return f"https://blob.test/{ref}"


class _Repos:
    def __init__(self, sessions, activities, media, boats, users):
        self.sessions = sessions
        self.activities = activities
        self.media = media
        self.boats = boats
        self.users = users


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            UserORM.__table__,
            UserRoleORM.__table__,  # UserORM.roles is lazy="selectin"
            BoatORM.__table__,
            UserBoatORM.__table__,  # BoatORM.members is lazy="selectin"
            ActivityORM.__table__,
            SessionORM.__table__,
            SessionUploadORM.__table__,  # sessions.primary_nav_upload_id FK target
            SessionPhotoORM.__table__,
            SessionCrewORM.__table__,  # is_session_crew_or_manager reads it
            ImageORM.__table__,
        ],
    )
    return sessionmaker(bind=engine, future=True)


@pytest.fixture
def repos(db):
    return _Repos(
        sessions=SqlSessionRepo(db),
        activities=SqlActivityRepo(db),
        media=SqlMediaRepo(db),
        boats=SqlBoatRepo(db),
        users=SqlUserRepo(db),
    )


@pytest.fixture(autouse=True)
def _fake_router_common(monkeypatch, repos):
    """Stand in for the real ``backend.routers._common.user_summary`` (see
    module docstring) with one backed by this test's own fixture DB, so
    ``media.session_photo_payload`` sees real names instead of crashing on
    import."""
    def user_summary(user_id):
        if user_id is None:
            return None
        u = repos.users.get_by_id(user_id)
        if u is None:
            return None
        return {"id": u.id, "first_name": u.first_name, "last_name": u.last_name,
                "email": u.email, "profile_image": None}

    fake_common = types.ModuleType("backend.routers._common")
    fake_common.user_summary = user_summary
    monkeypatch.setitem(sys.modules, "backend.routers", types.ModuleType("backend.routers"))
    monkeypatch.setitem(sys.modules, "backend.routers._common", fake_common)


@pytest.fixture(autouse=True)
def _wire_media(monkeypatch, repos):
    """``services/media.py`` resolves ``get_repos()``/``get_blob_store()`` at
    call time — point both at this test's fixtures instead of the real
    (DB/S3-backed) singletons."""
    import backend.services.media as media

    monkeypatch.setattr(media, "get_repos", lambda: repos)
    monkeypatch.setattr(media, "get_blob_store", lambda: _FakeBlobStore())
    return media


def _make_user(db, *, first_name="Sailor", email=None):
    with db() as s:
        u = UserORM(email=email or f"{uuid.uuid4()}@example.test", first_name=first_name,
                    last_name="Test", terms_and_conditions=True)
        s.add(u)
        s.commit()
        return u.id


def _make_boat(db, *, name="Aria", sail_number="ITA 1"):
    with db() as s:
        b = BoatORM(name=name, sail_number=sail_number)
        s.add(b)
        s.commit()
        return b.id


def _make_activity(db):
    with db() as s:
        a = ActivityORM(type="training")
        s.add(a)
        s.commit()
        return a.id


def _make_session(db, *, activity_id, boat_id):
    with db() as s:
        sess = SessionORM(activity_id=activity_id, boat_id=boat_id)
        s.add(sess)
        s.commit()
        return sess.id


def _make_image(repos, *, status="processed"):
    image = repos.media.create_image(created_by=None, ref="media/images/x")
    if status != "uploaded":
        repos.media.update_image(image.id, {"status": status})
    return image.id


def _add_photo(repos, session_id, *, created_by=None, image_status="processed",
              created_at=None):
    image_id = _make_image(repos, status=image_status)
    link = repos.sessions.add_photo(session_id, image_id=image_id, created_by=created_by)
    if created_at is not None:
        with repos.sessions.Session() as s:
            row = s.get(SessionPhotoORM, link.id)
            row.created_at = created_at
            s.commit()
            s.refresh(row)
            s.expunge(row)
            link = row
    return link


NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# --- session_photo_payload ---------------------------------------------------

def test_photo_row_carries_attribution_and_image_ref(repos, db, _wire_media):
    activity_id = _make_activity(db)
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)
    user_id = _make_user(db, first_name="Vela")
    link = _add_photo(repos, session_id, created_by=user_id)

    row = _wire_media.session_photo_payload(link)

    assert row["image_id"] == link.image_id
    assert row["url"] == "https://blob.test/media/images/x"
    assert row["created_at"] is not None
    assert row["created_by"] == user_id
    assert row["user"]["first_name"] == "Vela"


def test_photo_row_with_no_attribution_has_null_user(repos, db, _wire_media):
    activity_id = _make_activity(db)
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)
    link = _add_photo(repos, session_id, created_by=None)

    row = _wire_media.session_photo_payload(link)

    assert row["created_by"] is None
    assert row["user"] is None


def test_deleted_image_is_skipped(repos, db, _wire_media):
    activity_id = _make_activity(db)
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)
    link = _add_photo(repos, session_id, image_status="deleted")

    assert _wire_media.session_photo_payload(link) is None


def test_list_photos_is_oldest_first_and_carries_the_new_shape(repos, db, _wire_media):
    """Regression for GET /sessions/{id}/photos: image_id/url keep their
    existing meaning (older OTA bundles read them), created_at/created_by/user
    are additive."""
    activity_id = _make_activity(db)
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)
    older = _add_photo(repos, session_id, created_at=NOW - timedelta(days=1))
    newer = _add_photo(repos, session_id, created_at=NOW)

    ordered = repos.sessions.list_photos(session_id)

    assert [p.id for p in ordered] == [older.id, newer.id]
    rows = [_wire_media.session_photo_payload(p) for p in ordered]
    assert all({"image_id", "url", "created_at", "created_by", "user"} <= r.keys()
              for r in rows)


# --- list_photos_with_images (the endpoint's actual source) ------------------

def test_list_photos_with_images_joins_and_excludes_deleted(repos, db):
    """GET /sessions/{id}/photos reads this, not list_photos: the image is
    joined so a gallery costs one query instead of one per photograph, which
    also moves the deleted-image filter from the payload into the SQL."""
    activity_id = _make_activity(db)
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)
    older = _add_photo(repos, session_id, created_at=NOW - timedelta(days=1))
    newer = _add_photo(repos, session_id, created_at=NOW)
    _add_photo(repos, session_id, image_status="deleted", created_at=NOW)

    rows = repos.sessions.list_photos_with_images(session_id)

    assert [link.id for link, _img in rows] == [older.id, newer.id]
    assert all(img.id == link.image_id for link, img in rows)


def test_joined_image_builds_the_same_row_as_a_per_photo_lookup(repos, db, _wire_media):
    """The join is an efficiency change, not a shape change — passing the
    already-fetched image must produce exactly what fetching it per row did."""
    activity_id = _make_activity(db)
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)
    user_id = _make_user(db)
    _add_photo(repos, session_id, created_by=user_id)

    (link, image), = repos.sessions.list_photos_with_images(session_id)

    assert (_wire_media.session_photo_payload(link, image)
            == _wire_media.session_photo_payload(link))


# --- photo_covers (repository) ----------------------------------------------

def test_session_photo_covers_oldest_and_count(repos, db):
    activity_id = _make_activity(db)
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)
    older = _add_photo(repos, session_id, created_at=NOW - timedelta(days=2))
    _add_photo(repos, session_id, created_at=NOW - timedelta(days=1))
    _add_photo(repos, session_id, created_at=NOW)

    covers = repos.sessions.photo_covers([session_id])

    cover_image, count = covers[session_id]
    assert cover_image.id == older.image_id
    assert count == 3


def test_session_photo_covers_excludes_deleted_from_cover_and_count(repos, db):
    activity_id = _make_activity(db)
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)
    _add_photo(repos, session_id, image_status="deleted", created_at=NOW - timedelta(days=2))
    real = _add_photo(repos, session_id, created_at=NOW - timedelta(days=1))

    covers = repos.sessions.photo_covers([session_id])

    cover_image, count = covers[session_id]
    assert cover_image.id == real.image_id
    assert count == 1


def test_session_with_no_photos_is_absent_from_covers(repos, db):
    activity_id = _make_activity(db)
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)

    assert repos.sessions.photo_covers([session_id]) == {}


def test_activity_photo_covers_aggregate_across_sessions(repos, db):
    activity_id = _make_activity(db)
    boat_a = _make_boat(db, name="Aria")
    boat_b = _make_boat(db, name="Brezza")
    session_a = _make_session(db, activity_id=activity_id, boat_id=boat_a)
    session_b = _make_session(db, activity_id=activity_id, boat_id=boat_b)
    older = _add_photo(repos, session_a, created_at=NOW - timedelta(days=3))
    _add_photo(repos, session_b, created_at=NOW - timedelta(days=1))

    covers = repos.activities.photo_covers([activity_id])

    cover_image, count = covers[activity_id]
    assert cover_image.id == older.image_id
    assert count == 2


# --- activity_photos_payload (GET /activities/{id}/photos) -----------------

def test_activity_photos_span_two_sessions_and_two_boats(repos, db, _wire_media):
    activity_id = _make_activity(db)
    boat_a = _make_boat(db, name="Aria", sail_number="ITA 1")
    boat_b = _make_boat(db, name="Brezza", sail_number="ITA 2")
    session_a = _make_session(db, activity_id=activity_id, boat_id=boat_a)
    session_b = _make_session(db, activity_id=activity_id, boat_id=boat_b)
    older = _add_photo(repos, session_a, created_at=NOW - timedelta(hours=2))
    newer = _add_photo(repos, session_b, created_at=NOW - timedelta(hours=1))

    rows = _wire_media.activity_photos_payload(activity_id)

    assert [r["image_id"] for r in rows] == [older.image_id, newer.image_id]
    assert rows[0]["session_id"] == session_a
    assert rows[0]["boat"] == {"id": boat_a, "name": "Aria", "sail_number": "ITA 1"}
    assert rows[1]["session_id"] == session_b
    assert rows[1]["boat"] == {"id": boat_b, "name": "Brezza", "sail_number": "ITA 2"}


def test_activity_photos_skip_deleted_images(repos, db, _wire_media):
    activity_id = _make_activity(db)
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)
    _add_photo(repos, session_id, image_status="deleted")
    real = _add_photo(repos, session_id)

    rows = _wire_media.activity_photos_payload(activity_id)

    assert [r["image_id"] for r in rows] == [real.image_id]


# --- router wiring: reuses the existing visibility gate, doesn't add a new one --

def test_activity_photos_endpoint_gates_on_activity_visibility():
    """``GET /activities/{id}/photos`` must 404 an invisible activity the same
    way every other activity sub-resource does. Router-level HTTP execution
    isn't feasible in this suite (see ``test_admin_access_log.py``), so this
    checks the source directly: the handler must call the router's existing
    ``_require_visible`` (which wraps ``activity_visible_to``) rather than
    invent a second, possibly-inconsistent check."""
    import ast
    import pathlib

    path = (pathlib.Path(__file__).resolve().parents[2] / "backend" / "routers"
           / "activities.py")
    tree = ast.parse(path.read_text())

    handler = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "list_activity_photos":
            handler = node
            break
    assert handler is not None, "list_activity_photos not found — did it move/rename?"

    called = {n.func.id for n in ast.walk(handler)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_require_visible" in called


# --- session_photo_limit: the two-tier cap ----------------------------------

@pytest.fixture
def _wire_permissions(monkeypatch, repos):
    """``auth/permissions.py`` resolves ``get_repos()`` at call time too."""
    import backend.repositories as repositories

    monkeypatch.setattr(repositories, "get_repos", lambda: repos)
    from backend.auth import permissions

    return permissions


def _session_of(db, repos, *, created_by=None):
    with db() as s:
        a = ActivityORM(type="race", created_by=created_by)
        s.add(a)
        s.commit()
        activity_id = a.id
    boat_id = _make_boat(db)
    session_id = _make_session(db, activity_id=activity_id, boat_id=boat_id)
    with db() as s:
        return s.get(SessionORM, session_id)


def test_crew_member_gets_the_crew_cap(db, repos, _wire_permissions):
    user_id = _make_user(db)
    session = _session_of(db, repos)
    repos.sessions.add_crew(session.id, user_id=user_id, sailing_role="crew")
    user = repos.users.get_by_id(user_id)

    assert (_wire_permissions.session_photo_limit(session, user)
            == _wire_permissions.PHOTOS_PER_SESSION_CREW)


def test_activity_organiser_gets_the_higher_cap(db, repos, _wire_permissions):
    """The organiser posts the event's official set for every boat that
    sailed — a crew-sized cap would be the wrong shape for that."""
    organiser_id = _make_user(db)
    session = _session_of(db, repos, created_by=organiser_id)
    organiser = repos.users.get_by_id(organiser_id)

    assert (_wire_permissions.session_photo_limit(session, organiser)
            == _wire_permissions.PHOTOS_PER_SESSION_ORGANIZER)


def test_organiser_tier_wins_when_the_user_is_also_crew(db, repos, _wire_permissions):
    organiser_id = _make_user(db)
    session = _session_of(db, repos, created_by=organiser_id)
    repos.sessions.add_crew(session.id, user_id=organiser_id, sailing_role="skipper")
    organiser = repos.users.get_by_id(organiser_id)

    assert (_wire_permissions.session_photo_limit(session, organiser)
            == _wire_permissions.PHOTOS_PER_SESSION_ORGANIZER)


def test_unrelated_user_and_anonymous_may_add_none(db, repos, _wire_permissions):
    """None is the gate, not a cap of zero: this is the same answer the
    endpoint turns into a 403."""
    stranger = repos.users.get_by_id(_make_user(db))
    session = _session_of(db, repos)

    assert _wire_permissions.session_photo_limit(session, stranger) is None
    assert _wire_permissions.session_photo_limit(session, None) is None


def test_create_photo_enforces_the_cap_from_the_shared_policy():
    """The router must derive both the gate and the cap from
    ``session_photo_limit`` — a second, router-local notion of "organiser"
    would drift from the one tested above. Router-level HTTP execution isn't
    feasible here (see the visibility test above), so check the source."""
    import ast
    import pathlib

    path = (pathlib.Path(__file__).resolve().parents[2] / "backend" / "routers"
           / "sessions.py")
    tree = ast.parse(path.read_text())

    handler = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "create_photo"), None)
    assert handler is not None, "create_photo not found — did it move/rename?"

    called = {n.func.id for n in ast.walk(handler)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "session_photo_limit" in called
    # ...and it must actually compare the existing count against that limit.
    assert any(isinstance(n, ast.Compare) for n in ast.walk(handler))
    assert "photo_covers" in ast.unparse(handler)
