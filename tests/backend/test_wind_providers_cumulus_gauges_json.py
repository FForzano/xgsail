"""parse_realtime_gauges: JSON field extraction, unit conversion, and the
unambiguous ``timeUTC`` parsing that distinguishes this format from the
plain-text realtime.txt (see test_wind_providers_cumulus.py)."""

import json
from unittest.mock import Mock, patch

from backend.services.wind_providers import cumulus_gauges_json

# Trimmed version of a real CumulusMX realtimegauges.txt payload (kts units).
SAMPLE_PAYLOAD = {
    "date": "15:03:06",
    "temp": "29.7",
    "wlatest": "8.4",
    "wspeed": "10.5",
    "wgust": "13.8",
    "bearing": "100",
    "avgbearing": "82",
    "windunit": "kts",
    "tempunit": "C",
    "timeUTC": "2026,07,15,22,03,06",
}


def _payload(**overrides):
    data = {**SAMPLE_PAYLOAD, **overrides}
    return json.dumps(data)


def test_parses_wind_fields_and_observed_at_from_time_utc():
    result = cumulus_gauges_json.parse_realtime_gauges(_payload())
    assert result is not None
    assert result["twd_deg"] == 100.0
    assert result["tws_kts"] == 10.5
    assert result["gust_kts"] == 13.8
    assert result["observed_at"].isoformat() == "2026-07-15T22:03:06+00:00"


def test_mph_unit_converts_to_knots():
    result = cumulus_gauges_json.parse_realtime_gauges(_payload(windunit="mph"))
    assert result["tws_kts"] == round(10.5 * 0.868976, 1)


def test_invalid_json_returns_none():
    assert cumulus_gauges_json.parse_realtime_gauges("not json") is None


def test_missing_time_utc_returns_none():
    data = dict(SAMPLE_PAYLOAD)
    del data["timeUTC"]
    assert cumulus_gauges_json.parse_realtime_gauges(json.dumps(data)) is None


def test_malformed_time_utc_returns_none():
    result = cumulus_gauges_json.parse_realtime_gauges(_payload(timeUTC="not,a,date"))
    assert result is None


def test_unknown_wind_unit_returns_none():
    assert cumulus_gauges_json.parse_realtime_gauges(_payload(windunit="furlongs")) is None


def test_missing_wind_values_are_none_but_still_parses():
    data = dict(SAMPLE_PAYLOAD)
    del data["wspeed"]
    result = cumulus_gauges_json.parse_realtime_gauges(json.dumps(data))
    assert result is not None
    assert result["tws_kts"] is None
    assert result["gust_kts"] == 13.8


def test_fetch_station_parses_response_body():
    station = Mock(source_url="http://station.example/MBrealtimegauges.txt")
    resp = Mock(text=_payload())
    resp.raise_for_status = Mock()
    with patch("backend.services.wind_providers.cumulus_gauges_json.requests.get",
               return_value=resp) as mock_get:
        rows = cumulus_gauges_json.fetch_station(station)
    mock_get.assert_called_once_with(station.source_url,
                                     timeout=cumulus_gauges_json.FETCH_TIMEOUT_S)
    assert len(rows) == 1
    assert rows[0]["tws_kts"] == 10.5


def test_fetch_station_invalid_body_returns_no_rows():
    station = Mock(source_url="http://station.example/MBrealtimegauges.txt")
    resp = Mock(text="not json")
    resp.raise_for_status = Mock()
    with patch("backend.services.wind_providers.cumulus_gauges_json.requests.get",
               return_value=resp):
        rows = cumulus_gauges_json.fetch_station(station)
    assert rows == []
