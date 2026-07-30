"""Heart-rate zone derivation.

Two properties matter beyond the arithmetic: a *measured* maximum must never be
overridden by a population estimate, and the five bands must partition the range
so a given bpm falls in exactly one zone (the UI colours a trace by zone, and an
overlap would make that ambiguous).
"""

from datetime import date

import pytest

from backend.services.hr_zones import age_at, estimate_max_hr, hr_zones


class FakeUser:
    """Only the three profile fields hr_zones reads."""

    def __init__(self, dob=None, resting_hr_bpm=None, max_hr_bpm=None):
        self.dob = dob
        self.resting_hr_bpm = resting_hr_bpm
        self.max_hr_bpm = max_hr_bpm


SESSION_DAY = date(2026, 7, 30)


# --- age ------------------------------------------------------------------

def test_age_counts_whole_years_and_respects_the_session_date():
    assert age_at(date(1990, 1, 1), SESSION_DAY) == 36
    # Birthday not yet reached on the session date.
    assert age_at(date(1990, 12, 31), SESSION_DAY) == 35


def test_age_is_unknown_without_a_date_of_birth():
    assert age_at(None) is None


def test_implausible_dates_of_birth_are_rejected():
    assert age_at(date(2030, 1, 1), SESSION_DAY) is None  # in the future
    assert age_at(date(1800, 1, 1), SESSION_DAY) is None


def test_tanaka_is_used_not_220_minus_age():
    assert estimate_max_hr(40) == pytest.approx(180.0)
    # The two formulas happen to agree at 40; they diverge either side of it,
    # which is the whole reason for preferring Tanaka.
    assert estimate_max_hr(20) == pytest.approx(194.0)
    assert estimate_max_hr(20) < 220 - 20
    assert estimate_max_hr(70) > 220 - 70


# --- which maximum wins ---------------------------------------------------

def test_no_zones_without_either_a_measured_max_or_a_birth_date():
    assert hr_zones(FakeUser()) is None


def test_measured_max_beats_the_age_estimate():
    user = FakeUser(dob=date(1990, 1, 1), max_hr_bpm=195)
    zones = hr_zones(user, on=SESSION_DAY)
    assert zones["hr_max_bpm"] == 195
    assert zones["basis"] == "measured"


def test_measured_max_alone_is_enough_without_a_birth_date():
    zones = hr_zones(FakeUser(max_hr_bpm=190))
    assert zones["basis"] == "measured"
    assert zones["hr_max_bpm"] == 190


def test_age_estimate_is_labelled_as_an_estimate():
    zones = hr_zones(FakeUser(dob=date(1990, 1, 1)), on=SESSION_DAY)
    assert zones["basis"] == "tanaka"
    assert zones["hr_max_bpm"] == round(estimate_max_hr(36))


def test_zones_use_the_age_at_the_session_not_today():
    young = hr_zones(FakeUser(dob=date(1990, 1, 1)), on=date(2010, 7, 30))
    older = hr_zones(FakeUser(dob=date(1990, 1, 1)), on=date(2040, 7, 30))
    assert young["hr_max_bpm"] > older["hr_max_bpm"]


# --- which method lays out the bands -------------------------------------

def test_resting_rate_switches_to_heart_rate_reserve():
    zones = hr_zones(FakeUser(dob=date(1990, 1, 1), resting_hr_bpm=55), on=SESSION_DAY)
    assert zones["method"] == "hrr"
    # Karvonen floors zone 1 above the resting rate, well above the plain
    # 50%-of-max the other method would give.
    assert zones["zones"][0]["min_bpm"] > 55


def test_without_a_resting_rate_bands_are_percentages_of_maximum():
    zones = hr_zones(FakeUser(dob=date(1990, 1, 1)), on=SESSION_DAY)
    assert zones["method"] == "pct_max"
    # Bands come off the unrounded maximum (rounding only the reported figure),
    # so derive the expectation the same way rather than from hr_max_bpm.
    assert zones["zones"][0]["min_bpm"] == round(estimate_max_hr(36) * 0.50)


def test_an_implausible_resting_rate_falls_back_instead_of_producing_nonsense():
    """A resting rate at or near the maximum is a data-entry slip; a reserve of
    a few beats would compress all five zones into nothing."""
    zones = hr_zones(FakeUser(max_hr_bpm=180, resting_hr_bpm=175))
    assert zones["method"] == "pct_max"


# --- band geometry --------------------------------------------------------

def _all_variants():
    return [
        hr_zones(FakeUser(dob=date(1990, 1, 1)), on=SESSION_DAY),
        hr_zones(FakeUser(dob=date(1990, 1, 1), resting_hr_bpm=55), on=SESSION_DAY),
        hr_zones(FakeUser(max_hr_bpm=195, resting_hr_bpm=48)),
    ]


@pytest.mark.parametrize("zones", _all_variants())
def test_five_bands_numbered_one_to_five(zones):
    assert [z["zone"] for z in zones["zones"]] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("zones", _all_variants())
def test_bands_are_contiguous_and_never_overlap(zones):
    bands = zones["zones"]
    for lower, upper in zip(bands, bands[1:]):
        assert lower["max_bpm"] < upper["min_bpm"], "bands overlap"
        assert upper["min_bpm"] - lower["max_bpm"] == 1, "gap between bands"


@pytest.mark.parametrize("zones", _all_variants())
def test_bands_rise_and_top_out_at_the_maximum(zones):
    bands = zones["zones"]
    for band in bands:
        assert band["min_bpm"] <= band["max_bpm"]
    assert bands[-1]["max_bpm"] == zones["hr_max_bpm"]


@pytest.mark.parametrize("zones", _all_variants())
def test_every_bpm_inside_the_range_lands_in_exactly_one_band(zones):
    bands = zones["zones"]
    for bpm in range(bands[0]["min_bpm"], bands[-1]["max_bpm"] + 1):
        matches = [z for z in bands if z["min_bpm"] <= bpm <= z["max_bpm"]]
        assert len(matches) == 1, f"{bpm} bpm matched {len(matches)} zones"
