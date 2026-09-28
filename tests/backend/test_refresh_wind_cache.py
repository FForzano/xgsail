"""Regression: ``ingestion.refresh_wind_cache`` must sample GPS from the
session's resolved navigation upload (``nav_source.resolve_nav_upload``),
not simply the most recently uploaded one. A phone + Apple Watch pair
uploads the watch's physiological stream last — that upload has no
``gps.json`` at all, so picking by upload recency used to fail with
"No GPS track to sample wind from" even though the boat/phone's track was
sitting right there. No database: ``get_repos``/``get_blob_store`` and
``nav_source.resolve_nav_upload`` are patched, in the style of
test_wind_multi_station.py."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services import ingestion


def _session(started_at, ended_at=None):
    return SimpleNamespace(started_at=started_at, ended_at=ended_at,
                           trim_start_time=None, trim_end_time=None)


def test_refresh_wind_cache_uses_the_resolved_nav_upload_not_the_newest_upload():
    session_id = uuid.uuid4()
    boat_upload_id = uuid.uuid4()  # older upload, but the one that actually has GPS
    session = _session(datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
                       datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc))
    repos = SimpleNamespace(sessions=SimpleNamespace(get=lambda sid: session))
    boat_upload = SimpleNamespace(id=boat_upload_id)
    points = [{"lat": 45.0, "lon": 9.0}, {"lat": 45.01, "lon": 9.01}]
    fake_store = SimpleNamespace(get_json=lambda key: points)

    with patch("backend.services.ingestion.get_repos", return_value=repos), \
         patch("backend.services.ingestion.nav_source.resolve_nav_upload",
               return_value=boat_upload) as resolve, \
         patch("backend.services.ingestion.get_blob_store", return_value=fake_store), \
         patch("backend.services.ingestion.write_wind_cache") as write_cache, \
         patch("backend.services.ingestion.dispatch_analysis") as dispatch:
        prefix = ingestion.refresh_wind_cache(session_id)

    resolve.assert_called_once_with(session_id)
    assert prefix == ingestion.processed_prefix(boat_upload_id)
    write_cache.assert_called_once()
    assert write_cache.call_args.args[0] == prefix
    dispatch.assert_called_once()


def test_refresh_wind_cache_raises_when_no_upload_has_a_nav_track():
    session_id = uuid.uuid4()
    session = _session(datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc))
    repos = SimpleNamespace(sessions=SimpleNamespace(get=lambda sid: session))

    with patch("backend.services.ingestion.get_repos", return_value=repos), \
         patch("backend.services.ingestion.nav_source.resolve_nav_upload", return_value=None):
        with pytest.raises(ValueError, match="No processed data"):
            ingestion.refresh_wind_cache(session_id)


def test_refresh_wind_cache_raises_when_resolved_upload_has_no_gps_json():
    session_id = uuid.uuid4()
    session = _session(datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc))
    repos = SimpleNamespace(sessions=SimpleNamespace(get=lambda sid: session))
    upload = SimpleNamespace(id=uuid.uuid4())

    def _missing(key):
        raise Exception("not found")

    with patch("backend.services.ingestion.get_repos", return_value=repos), \
         patch("backend.services.ingestion.nav_source.resolve_nav_upload", return_value=upload), \
         patch("backend.services.ingestion.get_blob_store",
               return_value=SimpleNamespace(get_json=_missing)):
        with pytest.raises(ValueError, match="No GPS track"):
            ingestion.refresh_wind_cache(session_id)
