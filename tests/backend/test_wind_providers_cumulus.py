"""parse_realtime_line: field extraction, unit conversion, and tolerance for
malformed/short lines — the trickiest part of the Cumulus realtime.txt
adapter given the format's per-station configurable units."""

from unittest.mock import Mock, patch

from backend.services.wind_providers import cumulus_realtime

# A realistic realtime.txt line (mph wind units) — fields 0-16 only matter
# here, trailing fields are version-dependent extras we never read.
SAMPLE_LINE_MPH = (
    "27/10/13 14:15:00 12.6 89 10.9 3.7 6.8 244 0.0 0.2 1024.4 WSW 3 "
    "mph C mb mm 1.7 1023.9 Falling"
)


def test_parses_wind_fields_and_converts_mph_to_knots():
    result = cumulus_realtime.parse_realtime_line(SAMPLE_LINE_MPH)
    assert result is not None
    assert result["twd_deg"] == 244.0
    assert result["tws_kts"] == 3.2   # 3.7 mph
    assert result["gust_kts"] == 5.9  # 6.8 mph
    assert result["observed_at"] is not None


def test_kts_unit_is_passed_through_unconverted():
    line = SAMPLE_LINE_MPH.replace(" mph ", " kts ")
    result = cumulus_realtime.parse_realtime_line(line)
    assert result["tws_kts"] == 3.7
    assert result["gust_kts"] == 6.8


def test_ms_unit_converts_to_knots():
    line = SAMPLE_LINE_MPH.replace(" mph ", " m/s ")
    result = cumulus_realtime.parse_realtime_line(line)
    assert result["tws_kts"] == round(3.7 * 1.94384, 1)


def test_short_line_returns_none():
    assert cumulus_realtime.parse_realtime_line("27/10/13 14:15:00 12.6") is None


def test_unknown_wind_unit_returns_none():
    line = SAMPLE_LINE_MPH.replace(" mph ", " furlongs/fortnight ")
    assert cumulus_realtime.parse_realtime_line(line) is None


def test_non_numeric_wind_fields_are_none_but_line_still_parses():
    parts = SAMPLE_LINE_MPH.split()
    parts[5] = "---"  # Cumulus uses this for a missing/uninitialized value
    line = " ".join(parts)
    result = cumulus_realtime.parse_realtime_line(line)
    assert result is not None
    assert result["tws_kts"] is None
    assert result["gust_kts"] == 5.9


def test_fetch_station_parses_last_non_empty_line():
    station = Mock(source_url="http://station.example/realtime.txt")
    resp = Mock(text=f"\n{SAMPLE_LINE_MPH}\n\n")
    resp.raise_for_status = Mock()
    with patch("backend.services.wind_providers.cumulus_realtime.requests.get",
               return_value=resp) as mock_get:
        rows = cumulus_realtime.fetch_station(station)
    mock_get.assert_called_once_with(station.source_url,
                                     timeout=cumulus_realtime.FETCH_TIMEOUT_S)
    assert len(rows) == 1
    assert rows[0]["tws_kts"] == 3.2


def test_fetch_station_empty_response_returns_no_rows():
    station = Mock(source_url="http://station.example/realtime.txt")
    resp = Mock(text="   \n\n")
    resp.raise_for_status = Mock()
    with patch("backend.services.wind_providers.cumulus_realtime.requests.get",
               return_value=resp):
        rows = cumulus_realtime.fetch_station(station)
    assert rows == []
