"""Which of several GPS tracks becomes a session's navigation track
(``backend/services/nav_source.py``).

The case that drives this: two crew members on the same boat each record the
outing on their phone. Both uploads are manual imports with
``subject_type="crew_member"``, so neither hardware criterion separates them —
the ranking has to decide on the data. Before ``session_streams.first_t``/
``last_t`` existed it decided on point count alone, so a phone that died
twenty minutes early won for having sampled faster while it ran.

Two layers, as in the rest of this suite: the sort key is pure and driven with
stand-in objects, and ``nav_candidates`` is exercised end-to-end over in-memory
SQLite with real repos and a monkeypatched ``get_repos``.
"""

import types
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import (
    ActivityORM,
    BoatORM,
    ImportORM,
    SessionORM,
    SessionStreamORM,
    SessionUploadORM,
    UserBoatORM,
)
from backend.repositories.sql.ingest_repo import SqlIngestRepo
from backend.repositories.sql.session_repo import SqlSessionRepo
from backend.services import nav_source

# Naive on purpose: SQLite drops tzinfo on a DateTime(timezone=True) round
# trip, and these values are compared against freshly built ones. Same
# reasoning as test_ingestion_crew.py.
T0 = datetime(2026, 1, 1, 10, 0, 0)


def _dt(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def _stream(*, first_t=None, last_t=None, row_count=0):
    return types.SimpleNamespace(first_t=first_t, last_t=last_t, row_count=row_count)


def _upload(*, subject_type="crew_member", uploaded_at=T0, upload_id=None):
    return types.SimpleNamespace(id=upload_id or uuid.uuid4(),
                                 subject_type=subject_type, uploaded_at=uploaded_at)


def _session(start=T0, end=None):
    return types.SimpleNamespace(started_at=start, ended_at=end or _dt(120))


# --- covered_seconds --------------------------------------------------------

def test_coverage_is_clamped_to_the_session_window():
    """A device with a bad clock reporting points hours outside the outing
    must not buy coverage the session never had."""
    session = _session()  # 120 minutes
    stream = _stream(first_t=_dt(-600), last_t=_dt(600))

    assert nav_source.covered_seconds(stream, session) == 120 * 60


def test_coverage_is_zero_without_measured_bounds():
    assert nav_source.covered_seconds(_stream(), _session()) == 0.0


# --- the sort key -----------------------------------------------------------

def test_coverage_beats_density():
    """The whole point: a denser track that stopped early loses to a complete
    one."""
    session = _session()
    truncated = (_upload(), _stream(first_t=T0, last_t=_dt(100), row_count=100_000))
    complete = (_upload(), _stream(first_t=T0, last_t=_dt(120), row_count=7_000))

    ranked = sorted(
        [truncated, complete],
        key=lambda p: nav_source._rank(p[0], p[1], {}, session, True),
    )

    assert ranked[0] is complete


def test_density_decides_at_equal_coverage():
    """Point count did not stop mattering — it stopped coming first."""
    session = _session()
    sparse = (_upload(), _stream(first_t=T0, last_t=_dt(120), row_count=2_000))
    dense = (_upload(), _stream(first_t=T0, last_t=_dt(120), row_count=9_000))

    ranked = sorted([sparse, dense],
                    key=lambda p: nav_source._rank(p[0], p[1], {}, session, True))

    assert ranked[0] is dense


def test_a_wearable_still_loses_to_a_boat_track_however_complete():
    """Coverage is criterion 3, below the hardware ones: a wrist is a wrist."""
    session = _session()
    watch_id = uuid.uuid4()
    watch = (_upload(upload_id=watch_id), _stream(first_t=T0, last_t=_dt(120), row_count=50_000))
    tracker = (_upload(subject_type="boat"), _stream(first_t=T0, last_t=_dt(60), row_count=100))

    ranked = sorted(
        [watch, tracker],
        key=lambda p: nav_source._rank(p[0], p[1], {watch_id: "wearable"}, session, True),
    )

    assert ranked[0] is tracker


def test_recency_never_decides():
    """The module's standing invariant: a later upload must not swap out the
    track of a session that has already been analysed."""
    session = _session()
    early = (_upload(uploaded_at=T0), _stream(first_t=T0, last_t=_dt(120), row_count=5_000))
    late = (_upload(uploaded_at=_dt(999)), _stream(first_t=T0, last_t=_dt(120), row_count=5_000))

    ranked = sorted([late, early],
                    key=lambda p: nav_source._rank(p[0], p[1], {}, session, True))

    assert ranked[0] is early


def test_without_coverage_the_key_is_the_old_one():
    """``use_coverage=False`` must reproduce the pre-existing ordering exactly:
    boat before crew, then point count, then upload time."""
    session = _session()
    dense = (_upload(), _stream(first_t=T0, last_t=_dt(10), row_count=100_000))
    complete = (_upload(), _stream(first_t=T0, last_t=_dt(120), row_count=7_000))

    ranked = sorted([complete, dense],
                    key=lambda p: nav_source._rank(p[0], p[1], {}, session, False))

    assert ranked[0] is dense


# --- nav_candidates end to end ----------------------------------------------

@pytest.fixture
def repos():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        ActivityORM.__table__,
        BoatORM.__table__,
        ImportORM.__table__,
        SessionORM.__table__,
        SessionUploadORM.__table__,
        SessionStreamORM.__table__,
        UserBoatORM.__table__,  # BoatORM.members is lazy="selectin"
    ])
    Session = sessionmaker(bind=engine, future=True)
    return types.SimpleNamespace(
        ingest=SqlIngestRepo(Session),
        sessions=SqlSessionRepo(Session),
        devices=types.SimpleNamespace(get=lambda _id: None,
                                      get_type=lambda _id: None),
    ), Session


def _seed(repo, Session, *, tracks):
    """One session with an upload+gps stream per entry in ``tracks``.

    Returns the session id and the upload ids in the order given."""
    with Session() as s:
        boat = BoatORM(name="Test Boat")
        activity = ActivityORM(type="solo", visibility="private")
        s.add_all([boat, activity])
        s.commit()
        session = SessionORM(activity_id=activity.id, boat_id=boat.id,
                             started_at=T0, ended_at=_dt(120))
        s.add(session)
        s.commit()
        session_id = session.id

    upload_ids = []
    for spec in tracks:
        imp = ImportORM(original_filename="t.gpx")
        with Session() as s:
            s.add(imp)
            s.commit()
            import_id = imp.id
        upload = repo.ingest.create_upload({
            "session_id": session_id, "source_type": "manual_import",
            "import_id": import_id, "subject_type": "crew_member",
            "subject_user_id": uuid.uuid4(), "status": "processed",
        })
        repo.ingest.upsert_streams(upload.id, [{
            "sensor_type": "gps", "data_ref": f"processed/uploads/{upload.id}/gps.json",
            "row_count": spec["row_count"],
            "first_t": spec.get("first_t"), "last_t": spec.get("last_t"),
        }])
        upload_ids.append(upload.id)
    return session_id, upload_ids


def test_truncated_dense_track_does_not_win(repos, monkeypatch):
    repo, Session = repos
    monkeypatch.setattr(nav_source, "get_repos", lambda: repo)
    session_id, (truncated, complete) = _seed(repo, Session, tracks=[
        {"row_count": 100_000, "first_t": T0, "last_t": _dt(100)},
        {"row_count": 7_000, "first_t": T0, "last_t": _dt(120)},
    ])

    assert nav_source.resolve_nav_upload(session_id).id == complete


def test_unmeasured_streams_rank_exactly_as_before(repos, monkeypatch):
    """No candidate carries bounds — the coverage criterion is skipped, and
    the densest track wins as it always did."""
    repo, Session = repos
    monkeypatch.setattr(nav_source, "get_repos", lambda: repo)
    session_id, (dense, sparse) = _seed(repo, Session, tracks=[
        {"row_count": 100_000},
        {"row_count": 7_000},
    ])

    assert nav_source.resolve_nav_upload(session_id).id == dense


def test_a_single_unmeasured_stream_disables_the_coverage_criterion(repos, monkeypatch):
    """Mixed data must not let "written after the columns existed" decide the
    track: with one span unknown, the ranking falls back to the old key rather
    than scoring the unmeasured stream as covering nothing."""
    repo, Session = repos
    monkeypatch.setattr(nav_source, "get_repos", lambda: repo)
    session_id, (legacy_dense, measured_complete) = _seed(repo, Session, tracks=[
        {"row_count": 100_000},
        {"row_count": 7_000, "first_t": T0, "last_t": _dt(120)},
    ])

    assert nav_source.resolve_nav_upload(session_id).id == legacy_dense
