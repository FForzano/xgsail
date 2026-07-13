"""Unit tests for the shared wind-fusion package. Pure math, no I/O — these
run identically against the copy installed in the worker and backend images."""

import math

import pytest

import xgsail_windfusion as wf


@pytest.mark.parametrize("twd,tws", [(0, 10), (90, 5), (180, 12), (270, 3), (45, 8), (359, 1)])
def test_to_uv_from_uv_roundtrip(twd, tws):
    u, v = wf.to_uv(twd, tws)
    twd2, tws2 = wf.from_uv(u, v)
    assert twd2 == pytest.approx(twd, abs=1e-9)
    assert tws2 == pytest.approx(tws, abs=1e-9)


def test_from_uv_normalizes_direction_to_0_360():
    # A due-south-blowing-from wind vector: twd should be 180, not -180.
    twd, tws = wf.from_uv(*wf.to_uv(180, 5))
    assert 0.0 <= twd < 360.0


def test_weighted_mean_averages_in_vector_space_not_degrees():
    # The whole point: 350 and 10 must fuse to ~0/360, never 180.
    twd, tws, conf = wf.weighted_wind_mean([(350, 10, 1.0), (10, 10, 1.0)])
    assert min(twd, 360 - twd) < 1.0          # within 1 deg of North
    assert tws == pytest.approx(10 * math.cos(math.radians(10)), abs=1e-6)  # slight cancellation
    assert conf == pytest.approx(2.0)


def test_weighted_mean_high_weight_dominates():
    twd, _, _ = wf.weighted_wind_mean([(0, 10, 10.0), (90, 10, 0.1)])
    assert twd < 5.0 or twd > 355.0


def test_weighted_mean_confidence_is_total_contributing_weight():
    _, _, conf = wf.weighted_wind_mean([(0, 5, 0.7), (0, 5, 0.3)])
    assert conf == pytest.approx(1.0)


def test_weighted_mean_returns_none_when_nothing_usable():
    assert wf.weighted_wind_mean([]) is None
    assert wf.weighted_wind_mean([(10, 5, 0.0)]) is None          # zero weight
    assert wf.weighted_wind_mean([(10, None, 1.0)]) is None       # missing speed
    assert wf.weighted_wind_mean([(None, 5, 1.0)]) is None        # missing direction


def test_weighted_mean_skips_only_the_degenerate_contributions():
    # One good, one zero-weight — the good one still fuses.
    twd, tws, conf = wf.weighted_wind_mean([(90, 6, 1.0), (270, 99, 0.0)])
    assert twd == pytest.approx(90.0)
    assert tws == pytest.approx(6.0)
    assert conf == pytest.approx(1.0)


def test_source_weight_prior_ordering():
    base = {k: wf.source_weight(k) for k in wf.SOURCE_PRIORS}
    assert (base["onboard_sensor"] >= base["real_station"]
            > base["model_regional"] > base["model_global"]
            > base["gps_estimate"])


def test_source_weight_unknown_type_is_small_but_nonzero():
    w = wf.source_weight("something_new")
    assert 0.0 < w < wf.SOURCE_PRIORS["gps_estimate"]


def test_source_weight_decays_monotonically_with_distance():
    w = [wf.source_weight("real_station", distance_km=d) for d in (0, 5, 15, 40)]
    assert w[0] > w[1] > w[2] > w[3] > 0.0


def test_source_weight_decays_symmetrically_with_time_offset():
    near = wf.source_weight("model_regional", dt_seconds=60)
    far = wf.source_weight("model_regional", dt_seconds=3600)
    assert near > far > 0.0
    # sign of dt doesn't matter — |dt| is what counts
    assert wf.source_weight("model_regional", dt_seconds=600) == pytest.approx(
        wf.source_weight("model_regional", dt_seconds=-600))


def test_source_weight_scales_with_internal_confidence():
    full = wf.source_weight("grid_estimate", internal_confidence=1.0)
    half = wf.source_weight("grid_estimate", internal_confidence=0.5)
    assert half == pytest.approx(full * 0.5)
    # negative confidence is clamped to zero, never negative weight
    assert wf.source_weight("grid_estimate", internal_confidence=-1.0) == 0.0
