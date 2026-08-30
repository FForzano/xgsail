"""parse_ndbc_line: the ``MM`` missing-value marker is not the only way this
feed reports "no reading" — a value that parses but is out of range must be
dropped too, per field."""

from backend.services.wind_providers import ndbc

HEADER = "YY MM DD hh mm WDIR WSPD GST WVHT DPD APD MWD PRES ATMP".split()


def _line(wdir="240", wspd="5.0", gst="7.0"):
    return f"2026 08 30 11 00 {wdir} {wspd} {gst} MM MM MM MM 1013.0 24.0"


def test_parses_wind_fields_and_converts_m_s_to_knots():
    result = ndbc.parse_ndbc_line(HEADER, _line())
    assert result["twd_deg"] == 240.0
    assert result["tws_kts"] == 9.7   # 5.0 m/s
    assert result["gust_kts"] == 13.6  # 7.0 m/s


def test_mm_marks_a_missing_value():
    result = ndbc.parse_ndbc_line(HEADER, _line(wdir="MM"))
    assert result["twd_deg"] is None
    assert result["tws_kts"] == 9.7


def test_out_of_range_direction_is_dropped_without_losing_the_speeds():
    result = ndbc.parse_ndbc_line(HEADER, _line(wdir="999"))
    assert result["twd_deg"] is None
    assert result["tws_kts"] == 9.7
    assert result["gust_kts"] == 13.6


def test_negative_speed_is_dropped():
    result = ndbc.parse_ndbc_line(HEADER, _line(wspd="-9999"))
    assert result["tws_kts"] is None
    assert result["twd_deg"] == 240.0
