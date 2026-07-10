"""write_wind_cache: partial-failure merge against the previous cache —
a waypoint whose fetch raises falls back to its own prior bundle instead of
being dropped; a waypoint that succeeds (even with legitimately empty
sources) is never overridden by stale data."""

from unittest.mock import patch

import pytest

from backend.services import ingestion


class FakeStore:
    """Minimal BlobStore stand-in: an in-memory dict keyed by blob path."""

    def __init__(self, initial: dict = None):
        self._blobs = dict(initial or {})

    def get_json(self, key):
        if key not in self._blobs:
            raise KeyError(key)  # mimics BlobNotFound for this test's purposes
        return self._blobs[key]

    def put_bytes(self, key, data, content_type):
        import json
        self._blobs[key] = json.loads(data)


PREFIX = "processed/uploads/test-upload/"
START = None
END = None


def _cell_of(lat, lng):
    return ingestion.wind_estimates.grid_cell(lat, lng)


def test_no_previous_cache_failure_drops_the_cell_as_before():
    store = FakeStore()  # no prior wind_cache.json
    with patch("backend.services.ingestion.get_blob_store", return_value=store), \
         patch("backend.services.ingestion.wind_lookup.gather_raw_wind",
               side_effect=RuntimeError("provider trimmed history")):
        ingestion.write_wind_cache(PREFIX, [(45.0, 9.0)], START, END)
    # Nothing succeeded and nothing to fall back to -> no file written at all.
    assert f"{PREFIX}wind_cache.json" not in store._blobs


def test_partial_failure_falls_back_to_previous_bundle_for_that_cell():
    old_bundle = {
        "lat": 45.0, "lng": 9.0,
        "real_stations": [{"observed_at": "2026-07-01T10:00:00+00:00",
                           "twd_deg": 200, "tws_kts": 12}],
        "model_candidates": {}, "grid_estimates": [],
    }
    store = FakeStore({f"{PREFIX}wind_cache.json": [old_bundle]})

    with patch("backend.services.ingestion.get_blob_store", return_value=store), \
         patch("backend.services.ingestion.wind_lookup.gather_raw_wind",
               side_effect=RuntimeError("provider trimmed history")):
        ingestion.write_wind_cache(PREFIX, [(45.0, 9.0)], START, END)

    new_payload = store._blobs[f"{PREFIX}wind_cache.json"]
    assert len(new_payload) == 1
    assert new_payload[0] == old_bundle  # carried over verbatim, own observed_at intact


def test_successful_fetch_overwrites_the_old_bundle_not_merged_with_it():
    old_bundle = {"lat": 45.0, "lng": 9.0,
                 "real_stations": [{"observed_at": "old", "twd_deg": 200, "tws_kts": 12}],
                 "model_candidates": {}, "grid_estimates": []}
    fresh_bundle = {"real_stations": [{"observed_at": "new", "twd_deg": 10, "tws_kts": 8}],
                    "model_candidates": {}, "grid_estimates": []}
    store = FakeStore({f"{PREFIX}wind_cache.json": [old_bundle]})

    with patch("backend.services.ingestion.get_blob_store", return_value=store), \
         patch("backend.services.ingestion.wind_lookup.gather_raw_wind",
               return_value=fresh_bundle):
        ingestion.write_wind_cache(PREFIX, [(45.0, 9.0)], START, END)

    new_payload = store._blobs[f"{PREFIX}wind_cache.json"]
    assert len(new_payload) == 1
    assert new_payload[0]["real_stations"][0]["observed_at"] == "new"


def test_legitimately_empty_result_is_not_treated_as_a_failure():
    # gather_raw_wind succeeds but genuinely found nothing (no station in
    # range anymore) -> must NOT resurrect the old bundle.
    old_bundle = {"lat": 45.0, "lng": 9.0,
                 "real_stations": [{"observed_at": "old", "twd_deg": 200, "tws_kts": 12}],
                 "model_candidates": {}, "grid_estimates": []}
    empty_bundle = {"real_stations": [], "model_candidates": {}, "grid_estimates": []}
    store = FakeStore({f"{PREFIX}wind_cache.json": [old_bundle]})

    with patch("backend.services.ingestion.get_blob_store", return_value=store), \
         patch("backend.services.ingestion.wind_lookup.gather_raw_wind",
               return_value=empty_bundle):
        ingestion.write_wind_cache(PREFIX, [(45.0, 9.0)], START, END)

    new_payload = store._blobs[f"{PREFIX}wind_cache.json"]
    assert new_payload[0]["real_stations"] == []  # not the old station


def test_partial_failure_across_multiple_cells_mixes_fresh_and_stale():
    old_a = {"lat": 45.0, "lng": 9.0, "real_stations": [{"observed_at": "old_a"}],
            "model_candidates": {}, "grid_estimates": []}
    old_b = {"lat": 46.0, "lng": 10.0, "real_stations": [{"observed_at": "old_b"}],
            "model_candidates": {}, "grid_estimates": []}
    store = FakeStore({f"{PREFIX}wind_cache.json": [old_a, old_b]})

    def gather(lat, lng, start, end, gps_points=None):
        if lat == 45.0:
            raise RuntimeError("cell A's provider failed this time")
        return {"real_stations": [{"observed_at": "fresh_b"}], "model_candidates": {}, "grid_estimates": []}

    with patch("backend.services.ingestion.get_blob_store", return_value=store), \
         patch("backend.services.ingestion.wind_lookup.gather_raw_wind", side_effect=gather):
        ingestion.write_wind_cache(PREFIX, [(45.0, 9.0), (46.0, 10.0)], START, END)

    new_payload = store._blobs[f"{PREFIX}wind_cache.json"]
    by_lat = {e["lat"]: e for e in new_payload}
    assert by_lat[45.0]["real_stations"][0]["observed_at"] == "old_a"     # fell back
    assert by_lat[46.0]["real_stations"][0]["observed_at"] == "fresh_b"   # updated
