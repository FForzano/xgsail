"""An analysis the worker refused for lack of any wind source
(``analysis_unavailable: "no_wind_data"``), ``backend/services/session_analysis.py``.

Database-free, following ``test_track_wind_observations.py``: an in-memory
SQLite engine and the real ``SqlSessionRepo`` over the real ORM tables.
``routers/system.py`` and ``routers/sessions.py`` cannot be imported here (see
``test_admin_access_log.py``), which is why the fan-out lives in the service.
``GET /sessions/{id}/analysis`` serves ``SessionAnalysisORM.to_dict()``
verbatim, so the wire field is checked on that. The polar repo is faked: its
``owner_exactly_one`` CHECK uses Postgres' ``num_nonnulls``.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models import (
    SessionAnalysisORM, SessionLegORM, SessionManeuverORM, SessionStatsORM,
)
from backend.repositories.sql.session_repo import SqlSessionRepo
from backend.services import session_analysis

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


class FakePolars:
    def __init__(self):
        self.curves = {}

    def bulk_upsert(self, *, session_id, source, points):
        self.curves[session_id] = list(points)
        return len(points)


@pytest.fixture
def repos():
    engine = create_engine("sqlite:///:memory:")
    # sessions is not created: SQLite does not enforce the FK by default.
    Base.metadata.create_all(engine, tables=[
        SessionStatsORM.__table__, SessionManeuverORM.__table__,
        SessionLegORM.__table__, SessionAnalysisORM.__table__,
    ])
    fake = SimpleNamespace(sessions=SqlSessionRepo(sessionmaker(bind=engine, future=True)),
                           polars=FakePolars())
    with patch("backend.services.session_analysis.get_repos", return_value=fake):
        yield fake


def _maneuver(t=100.0):
    return {"maneuver_type": "tack", "start_time": t, "end_time": t + 10, "duration_sec": 10,
            "speed_loss_kts": 1.0, "speed_before_kts": 5.0, "speed_min_kts": 4.0,
            "speed_after_kts": 5.0, "recovery_time_sec": 8.0, "heading_change_deg": 90.0}


def _leg():
    return {"leg_type": "upwind", "start_time": 0.0, "end_time": 60.0, "duration_sec": 60.0,
            "distance_nm": 0.1, "avg_speed_kts": 5.0, "max_speed_kts": 6.0,
            "avg_vmg_kts": 3.5}


def _full_payload():
    return {
        "summary": {"distance_m": 5000.0, "avg_speed_kts": 5.0, "max_speed_kts": 7.0,
                    "duration_s": 3600, "avg_polar_pct": 80.0, "max_polar_pct": 95.0},
        "maneuvers": [_maneuver()],
        "legs": [_leg()],
        "polar_points": [{"twa_deg": 45, "tws_kts": 10, "speed_kts": 5}],
        "polar_target": [{"twa_deg": 45, "tws_kts": 10, "speed_kts": 6}],
        "vmg_series": [{"t": 0, "vmg": 3.5}],
        "true_wind": [{"t": 0, "twd_deg": 200, "tws_kts": 10}],
        "session_stats": {"speed": {"mean": 5.0}},
    }


def _unavailable_payload():
    return {
        "analysis_unavailable": "no_wind_data",
        "summary": {"distance_m": 5200.0, "avg_speed_kts": 5.1, "max_speed_kts": 7.2,
                    "duration_s": 3600},
        "maneuvers": [], "legs": [], "polar_points": [], "polar_target": None,
        "vmg_series": None, "true_wind": None, "track_wind_observations": [],
    }


def test_unavailable_payload_stores_reason_and_clears_stale_results(repos):
    sid = uuid.uuid4()
    session_analysis.apply_payload(sid, _full_payload(), NOW)
    session_analysis.apply_payload(sid, _unavailable_payload(), NOW)

    analysis = repos.sessions.get_analysis(sid)
    assert analysis.unavailable_reason == "no_wind_data"
    assert analysis.true_wind is None
    assert analysis.vmg_series is None
    assert analysis.polar_target is None
    assert repos.sessions.list_maneuvers(sid) == []
    assert repos.sessions.list_legs(sid) == []
    assert repos.polars.curves[sid] == []

    stats = repos.sessions.get_stats(sid)
    assert stats.distance_m == 5200.0
    assert stats.avg_speed_kts == 5.1
    # Omitted by the summary, but must not survive from the previous run.
    assert stats.avg_polar_pct is None
    assert stats.max_polar_pct is None


def test_a_later_normal_analysis_resets_the_reason(repos):
    sid = uuid.uuid4()
    session_analysis.apply_payload(sid, _unavailable_payload(), NOW)
    session_analysis.apply_payload(sid, _full_payload(), NOW)

    analysis = repos.sessions.get_analysis(sid)
    assert analysis.unavailable_reason is None
    assert len(repos.sessions.list_maneuvers(sid)) == 1
    assert repos.sessions.get_stats(sid).avg_polar_pct == 80.0


def test_explicit_null_is_a_normal_analysis(repos):
    sid = uuid.uuid4()
    session_analysis.apply_payload(sid, {**_full_payload(), "analysis_unavailable": None}, NOW)
    assert repos.sessions.get_analysis(sid).unavailable_reason is None


def test_unknown_reason_is_dropped_rather_than_failing_the_upsert(repos):
    sid = uuid.uuid4()
    session_analysis.apply_payload(sid, {**_full_payload(), "analysis_unavailable": "later"},
                                   NOW)
    assert repos.sessions.get_analysis(sid).unavailable_reason is None


def test_get_analysis_wire_payload_exposes_the_field(repos):
    sid = uuid.uuid4()
    session_analysis.apply_payload(sid, _full_payload(), NOW)
    assert repos.sessions.get_analysis(sid).to_dict()["unavailable_reason"] is None

    session_analysis.apply_payload(sid, _unavailable_payload(), NOW)
    assert repos.sessions.get_analysis(sid).to_dict()["unavailable_reason"] == "no_wind_data"
