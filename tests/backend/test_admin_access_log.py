"""The superadmin diagnostics audit trail
(``backend/repositories/sql/admin_log_repo.py``, ``backend/routers/admin.py``).

Database-free, following ``test_live_recordings.py``: an in-memory SQLite
engine and the real repository over the real ORM table.

Router-level HTTP coverage is not feasible in this suite and is deliberately
not faked: importing ``backend.routers.admin`` pulls in ``routers/_common``,
which builds the repository facade (and therefore a live Postgres connection)
at import time, and there is no ``TestClient`` fixture anywhere in ``tests/``.
What *is* covered are the invariants that can be checked without running the
app, over the router's source: every handler calls ``require_superadmin``,
every handler is a GET, and the session summary carries no crew-note text.
``require_superadmin``'s own 401/403 behaviour belongs to
``backend/auth/permissions.py`` and is not re-tested here.
"""

import ast
import pathlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import AdminAccessLogORM, UserORM
from backend.repositories.sql.admin_log_repo import SqlAdminLogRepo

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

ADMIN_ROUTER = pathlib.Path(__file__).resolve().parents[2] / "backend" / "routers" / "admin.py"


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        UserORM.__table__,  # both FKs point at it
        AdminAccessLogORM.__table__,
    ])
    Session = sessionmaker(bind=engine, future=True)
    return SqlAdminLogRepo(Session), Session


def _stamp(Session, row_id, when):
    """SQLite fills every row's ``created_at`` from one ``now()``; the ordering
    test needs distinct values."""
    with Session() as s:
        s.get(AdminAccessLogORM, row_id).created_at = when
        s.commit()


def test_record_appends_one_row(repo):
    log, _ = repo
    actor, target = uuid.uuid4(), uuid.uuid4()

    row = log.record(actor_user_id=actor, target_user_id=target, action="user.boats")

    assert (row.actor_user_id, row.target_user_id, row.action) == (actor, target, "user.boats")
    assert row.created_at is not None
    assert len(log.list()) == 1


def test_list_filters_by_target_and_returns_newest_first(repo):
    log, Session = repo
    actor = uuid.uuid4()
    alice, bob = uuid.uuid4(), uuid.uuid4()

    older = log.record(actor_user_id=actor, target_user_id=alice, action="user.detail")
    _stamp(Session, older.id, NOW - timedelta(hours=1))
    newer = log.record(actor_user_id=actor, target_user_id=alice, action="user.sessions")
    _stamp(Session, newer.id, NOW)
    other = log.record(actor_user_id=actor, target_user_id=bob, action="user.detail")
    _stamp(Session, other.id, NOW + timedelta(hours=1))

    assert [r.id for r in log.list(target_user_id=alice)] == [newer.id, older.id]
    assert [r.id for r in log.list()] == [other.id, newer.id, older.id]


def test_list_paginates(repo):
    log, Session = repo
    target = uuid.uuid4()
    ids = []
    for i in range(3):
        row = log.record(actor_user_id=uuid.uuid4(), target_user_id=target,
                         action="user.activities")
        _stamp(Session, row.id, NOW + timedelta(minutes=i))
        ids.append(row.id)

    assert [r.id for r in log.list(limit=2)] == [ids[2], ids[1]]
    assert [r.id for r in log.list(limit=2, offset=2)] == [ids[0]]


def test_an_unattributed_actor_is_still_recorded(repo):
    """``require_superadmin`` returns None under ``SAILFRAMES_ADMIN_BYPASS``;
    the access still happened, so the row must survive a NULL actor."""
    log, _ = repo
    target = uuid.uuid4()

    row = log.record(actor_user_id=None, target_user_id=target, action="user.detail")

    assert row.actor_user_id is None
    assert [r.id for r in log.list(target_user_id=target)] == [row.id]


def _route_handlers(tree):
    """(http_method, function_node) for every ``@router.<verb>(...)`` handler."""
    out = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "router"):
                out.append((dec.func.attr, node))
    return out


def test_every_admin_endpoint_requires_superadmin():
    """A new admin endpoint added without the gate would hand another user's
    data to any authenticated caller."""
    handlers = _route_handlers(ast.parse(ADMIN_ROUTER.read_text()))
    assert handlers, "no @router handlers found — did admin.py move?"

    ungated = []
    for _method, node in handlers:
        called = {n.func.id for n in ast.walk(node)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        if "require_superadmin" not in called:
            ungated.append(node.name)

    assert ungated == []


def test_the_admin_router_serves_no_mutations():
    """Read-only surface: no impersonation, no admin edit of another user's
    data — so every handler is a GET."""
    handlers = _route_handlers(ast.parse(ADMIN_ROUTER.read_text()))

    assert {method for method, _ in handlers} == {"get"}


def test_a_session_summary_never_carries_note_text():
    """``sessions.notes`` is private to that session's crew and the boat's
    owner/admin — superadmin is not one of those audiences, so the summary
    reports only whether a note exists."""
    tree = ast.parse(ADMIN_ROUTER.read_text())
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_session_summary")
    keys = {n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}

    assert "has_notes" in keys
    assert "notes" not in keys
    assert "notes" not in attrs
