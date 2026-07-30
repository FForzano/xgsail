"""Aggregates for the Apple Watch physiological streams.

The interesting cases are the ones where the obvious implementation is wrong:
active energy is a cumulative counter that can restart mid-session, and the
sparse streams are nowhere near the 1 Hz the boat sensors report.
"""

import pytest

from processing.physio import cumulative_total, physio_stats, sample_rate_hz


def hr(*pairs):
    return [{"t": t, "bpm": v} for t, v in pairs]


def energy(*pairs):
    return [{"t": t, "kcal": v} for t, v in pairs]


# --- heart rate -----------------------------------------------------------

def test_heart_rate_min_avg_max_and_covered_span():
    out = physio_stats("heart_rate", hr(
        ("2026-07-24T10:00:00Z", 100),
        ("2026-07-24T10:00:05Z", 150),
        ("2026-07-24T10:10:00Z", 122),
    ))
    assert out["min_hr_bpm"] == 100.0
    assert out["max_hr_bpm"] == 150.0
    assert out["avg_hr_bpm"] == pytest.approx(124.0, abs=0.1)
    # The span the samples actually cover, not the session's duration.
    assert out["hr_duration_s"] == 600


def test_heart_rate_out_of_order_samples_are_sorted():
    """Merged output is sorted by the handler, but HealthKit stamps HR rows with
    wall-clock time at delivery, so don't rely on arrival order for the span."""
    out = physio_stats("heart_rate", hr(
        ("2026-07-24T10:10:00Z", 120),
        ("2026-07-24T10:00:00Z", 100),
    ))
    assert out["hr_duration_s"] == 600


def test_unparseable_rows_are_skipped_not_fatal():
    out = physio_stats("heart_rate", [
        {"t": "2026-07-24T10:00:00Z", "bpm": 100},
        {"t": "not-a-date", "bpm": 999},
        {"t": "2026-07-24T10:00:10Z", "bpm": None},
        {"t": "2026-07-24T10:00:20Z", "bpm": "120"},  # numeric string
    ])
    assert out["max_hr_bpm"] == 120.0
    assert out["hr_duration_s"] == 20


# --- active energy (cumulative) ------------------------------------------

def test_energy_totals_a_plain_rising_counter():
    out = physio_stats("energy", energy(
        ("2026-07-24T10:00:00Z", 0),
        ("2026-07-24T10:05:00Z", 50),
        ("2026-07-24T10:10:00Z", 120),
    ))
    assert out["total_kcal"] == 120.0
    assert out["avg_kcal_per_min"] == pytest.approx(12.0)


def test_energy_survives_a_counter_reset_midway():
    """The case that rules out ``last - first``.

    The watch restarting mid-outing sends the counter back to zero. Subtracting
    the endpoints would report only the energy burned after the restart (40),
    silently discarding the 80 kcal before it.
    """
    points = energy(
        ("2026-07-24T10:00:00Z", 0),
        ("2026-07-24T10:05:00Z", 80),
        ("2026-07-24T10:06:00Z", 0),   # restart
        ("2026-07-24T10:10:00Z", 40),
    )
    assert physio_stats("energy", points)["total_kcal"] == 120.0
    last_minus_first = points[-1]["kcal"] - points[0]["kcal"]
    assert last_minus_first == 40.0  # what the naive version would have said


def test_energy_single_sample_is_its_own_total():
    out = physio_stats("energy", energy(("2026-07-24T10:00:00Z", 37)))
    assert out["total_kcal"] == 37.0
    # No span, so no rate — better absent than a division by zero.
    assert "avg_kcal_per_min" not in out


def test_cumulative_total_ignores_a_lone_decrease():
    assert cumulative_total([(0, 10.0), (1, 4.0)]) == 0.0


# --- sparse streams -------------------------------------------------------

def test_hrv_and_respiration_are_averaged():
    assert physio_stats("hrv", [
        {"t": "2026-07-24T10:00:00Z", "ms": 40},
        {"t": "2026-07-24T10:09:00Z", "ms": 50},
    ])["avg_hrv_ms"] == 45.0
    assert physio_stats("respiration", [
        {"t": "2026-07-24T10:00:00Z", "brpm": 14},
    ])["avg_resp_brpm"] == 14.0


def test_sample_rate_reflects_a_sparse_series_not_1hz():
    """HRV arrives every few minutes; reporting 1.0 Hz (as the handler used to,
    for every sensor type) would have the UI claim a precision that isn't
    there."""
    rate = sample_rate_hz([
        {"t": "2026-07-24T10:00:00Z", "ms": 40},
        {"t": "2026-07-24T10:05:00Z", "ms": 42},
        {"t": "2026-07-24T10:10:00Z", "ms": 44},
    ], "hrv")
    # Reported to 3 decimals, hence the loose tolerance on a ~0.003 Hz rate.
    assert rate == pytest.approx(2 / 600, abs=1e-3)
    assert rate < 1.0


# --- degenerate input -----------------------------------------------------

@pytest.mark.parametrize("sensor", ["heart_rate", "energy", "hrv", "respiration"])
def test_empty_series_yields_no_keys(sensor):
    """An empty dict means "leave the stored row alone" — the four physio files
    arrive as independent callbacks that merge into one row."""
    assert physio_stats(sensor, []) == {}
    assert physio_stats(sensor, None) == {}


def test_non_physio_sensor_is_ignored():
    assert physio_stats("gps", [{"t": "2026-07-24T10:00:00Z", "lat": 43.0}]) == {}


def test_sample_rate_of_empty_or_single_series_is_unknown():
    assert sample_rate_hz([], "hrv") is None
    assert sample_rate_hz([{"t": "2026-07-24T10:00:00Z", "ms": 40}], "hrv") is None
