"""Undoing an automatic session merge (``backend/services/session_split.py``).

Two crew members recording one outing on the same boat land on a single
session by way of ``ingestion.find_or_create_session``'s boat+window match.
That is right far more often than not, but it has to be reversible — these
tests build the merge exactly as the app does and then take it apart again.

Database-free, following ``test_ingestion_crew.py``: in-memory SQLite, real
repositories, a ``SimpleNamespace`` standing in for the ``Repositories``
facade, and ``get_repos`` monkeypatched on every module that reaches for it.
``detach_upload`` does no worker dispatch of its own (the router schedules the
re-analyses), so nothing here needs the network mocked.
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
    SessionCrewORM,
    SessionORM,
    SessionPhotoORM,
    SessionPhysioStatsORM,
    SessionStreamORM,
    SessionUploadORM,
    SessionVideoORM,
    UserBoatORM,
)
from backend.repositories.sql.activity_repo import SqlActivityRepo
from backend.repositories.sql.boat_repo import SqlBoatRepo
from backend.repositories.sql.ingest_repo import SqlIngestRepo
from backend.repositories.sql.session_repo import SqlSessionRepo
from backend.services import ingestion, session_split

# Naive, for the SQLite tzinfo reason documented in test_ingestion_crew.py.
T0 = datetime(2026, 1, 1, 10, 0, 0)


def _dt(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


@pytest.fixture
def repos(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        ActivityORM.__table__,
        BoatORM.__table__,
        ImportORM.__table__,
        SessionORM.__table__,
        SessionUploadORM.__table__,
        SessionStreamORM.__table__,
        SessionPhysioStatsORM.__table__,
        SessionCrewORM.__table__,
        SessionPhotoORM.__table__,
        SessionVideoORM.__table__,
        UserBoatORM.__table__,  # BoatORM.members is lazy="selectin"
    ])
    Session = sessionmaker(bind=engine, future=True)
    repo = types.SimpleNamespace(
        activities=SqlActivityRepo(Session),
        boats=SqlBoatRepo(Session),
        sessions=SqlSessionRepo(Session),
        ingest=SqlIngestRepo(Session),
    )
    monkeypatch.setattr(ingestion, "get_repos", lambda: repo)
    monkeypatch.setattr(session_split, "get_repos", lambda: repo)
    return repo, Session


@pytest.fixture
def boat_id(repos):
    _, Session = repos
    with Session() as s:
        boat = BoatORM(name="Test Boat")
        s.add(boat)
        s.commit()
        return boat.id


def _add_recording(repo, Session, *, boat_id, user_id, start, end,
                   row_count=1000, activity_id=None):
    """One crew member's phone recording, uploaded the way RegistraPage does:
    a manual import attributed to themselves, resolved onto whatever session
    the boat+window match finds."""
    session = ingestion.find_or_create_session(
        boat_id=boat_id, started_at=start, ended_at=end,
        activity_id=activity_id, created_by=user_id,
    )
    with Session() as s:
        imp = ImportORM(original_filename="registrazione.gpx", uploaded_by=user_id)
        s.add(imp)
        s.commit()
        import_id = imp.id
    upload = repo.ingest.create_upload({
        "session_id": session.id, "source_type": "manual_import",
        "import_id": import_id, "subject_type": "crew_member",
        "subject_user_id": user_id, "status": "processed",
    })
    repo.ingest.upsert_streams(upload.id, [{
        "sensor_type": "gps", "data_ref": f"processed/uploads/{upload.id}/gps.json",
        "row_count": row_count, "first_t": start, "last_t": end,
    }])
    repo.ingest.upsert_physio_stats(upload.id, {"avg_hr_bpm": 130.0})
    repo.sessions.rollup_status(session.id)
    return session, upload


def _crew_ids(Session, session_id):
    with Session() as s:
        return {c.user_id for c in
                s.query(SessionCrewORM).filter(SessionCrewORM.session_id == session_id)}


@pytest.fixture
def merged(repos, boat_id):
    """The scenario: helm and bow both record, and the two uploads merge."""
    repo, Session = repos
    helm, bow = uuid.uuid4(), uuid.uuid4()
    session, helm_upload = _add_recording(
        repo, Session, boat_id=boat_id, user_id=helm,
        start=T0, end=_dt(120), row_count=7_000)
    also_session, bow_upload = _add_recording(
        repo, Session, boat_id=boat_id, user_id=bow,
        start=_dt(5), end=_dt(118), row_count=9_000)
    assert session.id == also_session.id, "precondition: the two uploads merged"
    return types.SimpleNamespace(
        session_id=session.id, helm=helm, bow=bow,
        helm_upload=helm_upload, bow_upload=bow_upload)


# --- the round trip ---------------------------------------------------------

def test_detach_moves_the_upload_and_its_data_to_a_new_session(repos, merged):
    repo, Session = repos

    result = session_split.detach_upload(
        merged.session_id, merged.bow_upload.id, user_id=merged.bow)

    new_id = result["session_id"]
    assert new_id != merged.session_id
    assert repo.ingest.get_upload(merged.bow_upload.id).session_id == new_id
    # Streams and physio stats are keyed on the upload, so they follow it.
    assert [s.id for s in repo.ingest.list_streams_for_session(new_id)] == \
        [s.id for s in repo.ingest.list_streams(merged.bow_upload.id)]
    assert repo.ingest.get_physio_stats(merged.bow_upload.id) is not None
    # The source keeps the other track.
    remaining = repo.ingest.list_uploads(session_id=merged.session_id)
    assert [u.id for u in remaining] == [merged.helm_upload.id]


def test_detach_puts_each_person_on_their_own_session(repos, merged):
    repo, Session = repos

    result = session_split.detach_upload(
        merged.session_id, merged.bow_upload.id, user_id=merged.bow)

    assert _crew_ids(Session, result["session_id"]) == {merged.bow}
    # The bow said they were not part of that outing; leaving them crewed on
    # it would keep it in their diary.
    assert _crew_ids(Session, merged.session_id) == {merged.helm}


def test_detach_keeps_a_contributor_who_still_has_data_on_the_source(repos, merged, boat_id):
    """Someone who uploaded twice — a phone and a watch, say — stays crew of
    the source session when only one of the two is pulled out."""
    repo, Session = repos
    _, second_bow_upload = _add_recording(
        repo, Session, boat_id=boat_id, user_id=merged.bow,
        start=_dt(10), end=_dt(115), row_count=500)

    session_split.detach_upload(merged.session_id, merged.bow_upload.id,
                                user_id=merged.bow)

    assert merged.bow in _crew_ids(Session, merged.session_id)
    assert repo.ingest.get_upload(second_bow_upload.id).session_id == merged.session_id


def test_source_window_shrinks_to_what_it_still_holds(repos, boat_id):
    """``extend_window`` only ever widens; after a detach the source would
    otherwise keep claiming time it has no track for."""
    repo, Session = repos
    early, late = uuid.uuid4(), uuid.uuid4()
    session, early_upload = _add_recording(
        repo, Session, boat_id=boat_id, user_id=early, start=T0, end=_dt(60))
    _, late_upload = _add_recording(
        repo, Session, boat_id=boat_id, user_id=late, start=_dt(50), end=_dt(180))
    assert repo.sessions.get(session.id).ended_at == _dt(180)

    session_split.detach_upload(session.id, late_upload.id, user_id=late)

    assert repo.sessions.get(session.id).ended_at == _dt(60)


def test_detached_session_gets_its_own_private_solo_activity(repos, merged):
    repo, _ = repos
    source_activity_id = repo.sessions.get(merged.session_id).activity_id

    result = session_split.detach_upload(
        merged.session_id, merged.bow_upload.id, user_id=merged.bow)

    assert result["activity_id"] != source_activity_id
    activity = repo.activities.get(result["activity_id"])
    assert (activity.type, activity.visibility) == ("solo", "private")
    assert activity.created_by == merged.bow


def test_detaching_out_of_a_shared_activity_keeps_that_activity(repos, boat_id):
    """A club training or a race is a real event the boat took part in.
    Moving a detached track into a private solo activity would quietly pull it
    out of that event's replay and data endpoints."""
    repo, Session = repos
    with Session() as s:
        race = ActivityORM(type="race", visibility="club",
                           started_at=T0, ended_at=_dt(120))
        s.add(race)
        s.commit()
        race_id = race.id
    helm, bow = uuid.uuid4(), uuid.uuid4()
    session, _ = _add_recording(repo, Session, boat_id=boat_id, user_id=helm,
                                start=T0, end=_dt(120), activity_id=race_id)
    _, bow_upload = _add_recording(repo, Session, boat_id=boat_id, user_id=bow,
                                   start=_dt(5), end=_dt(118), activity_id=race_id)

    result = session_split.detach_upload(session.id, bow_upload.id, user_id=bow)

    assert result["activity_id"] == race_id
    assert repo.sessions.get(result["session_id"]).activity_id == race_id


# --- the pointer that ON DELETE SET NULL does not cover ----------------------

def test_detach_moves_an_explicit_track_choice_with_the_upload(repos, merged):
    """``sessions.primary_nav_upload_id`` is a plain FK with ON DELETE SET
    NULL, and SET NULL does not fire on UPDATE: re-parenting an upload leaves
    the source pointing at a track it no longer owns. ``resolve_nav_upload``
    degrades quietly, which is exactly why this would go unnoticed."""
    repo, _ = repos
    repo.sessions.update(merged.session_id,
                         {"primary_nav_upload_id": merged.bow_upload.id})

    result = session_split.detach_upload(
        merged.session_id, merged.bow_upload.id, user_id=merged.bow)

    assert repo.sessions.get(merged.session_id).primary_nav_upload_id is None
    assert repo.sessions.get(result["session_id"]).primary_nav_upload_id == \
        merged.bow_upload.id


def test_detach_leaves_an_unrelated_track_choice_alone(repos, merged):
    repo, _ = repos
    repo.sessions.update(merged.session_id,
                         {"primary_nav_upload_id": merged.helm_upload.id})

    session_split.detach_upload(merged.session_id, merged.bow_upload.id,
                                user_id=merged.bow)

    assert repo.sessions.get(merged.session_id).primary_nav_upload_id == \
        merged.helm_upload.id


# --- refusals ---------------------------------------------------------------

def test_cannot_detach_the_only_upload(repos, boat_id):
    """Keeps "what if the source is left with nothing" unrepresentable rather
    than something to handle."""
    repo, Session = repos
    user = uuid.uuid4()
    session, upload = _add_recording(repo, Session, boat_id=boat_id, user_id=user,
                                     start=T0, end=_dt(120))

    with pytest.raises(ValueError, match="Nothing to separate"):
        session_split.detach_upload(session.id, upload.id, user_id=user)


def test_cannot_detach_an_upload_from_a_session_it_is_not_on(repos, merged, boat_id):
    repo, Session = repos
    other_session, other_upload = _add_recording(
        repo, Session, boat_id=boat_id, user_id=uuid.uuid4(),
        start=_dt(600), end=_dt(700))

    with pytest.raises(ValueError, match="Upload not found"):
        session_split.detach_upload(merged.session_id, other_upload.id,
                                    user_id=merged.bow)
