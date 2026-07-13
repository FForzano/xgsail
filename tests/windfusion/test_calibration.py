"""Leave-one-out calibration core: error metric, scoring, and that the search
actually recovers a better weight configuration from held-out data."""

import math

import pytest

import xgsail_windfusion as wf
from xgsail_windfusion import calibration as cal


@pytest.mark.parametrize("pred,true,expected", [
    (100, 100, 0), (350, 10, 20), (10, 350, 20), (0, 180, 180), (90, 270, 180),
])
def test_angular_error_wraps(pred, true, expected):
    assert cal.angular_error_deg(pred, true) == pytest.approx(expected)


def _site(truth_twd, contributions, truth_tws=None):
    return {"truth_twd": truth_twd, "truth_tws": truth_tws, "contributions": contributions}


def test_score_perfect_prediction_is_zero_error():
    sites = [_site(100, [{"twd": 100, "tws": 10, "source_type": "real_station",
                          "distance_km": 0, "dt_seconds": 0}], truth_tws=10)]
    s = cal.score(sites)
    assert s["twd_mae"] == pytest.approx(0.0)
    assert s["tws_mae"] == pytest.approx(0.0)
    assert s["n"] == 1


def test_score_infinite_when_nothing_predictable():
    # No usable contributions anywhere -> no site scored.
    s = cal.score([_site(100, [])])
    assert s["twd_mae"] == float("inf")
    assert s["n"] == 0


def _biased_station_sites(n=6):
    """Truth ~100°. The nearby 'real_station' is systematically 60° off; the
    regional model is spot-on. The shipped weights over-trust the station, so
    calibration should up-weight the model."""
    sites = []
    for i in range(n):
        truth = 100.0 + (i - n / 2)          # a little spread so it's not degenerate
        sites.append(_site(truth, [
            {"twd": truth + 60.0, "tws": 10, "source_type": "real_station", "distance_km": 1.0},
            {"twd": truth, "tws": 10, "source_type": "model_regional"},
        ], truth_tws=10))
    return sites


def test_default_config_is_pulled_toward_the_biased_station():
    sites = _biased_station_sites()
    # With the shipped priors the near station dominates -> sizeable error.
    assert cal.score(sites, wf.DEFAULT_CONFIG)["twd_mae"] > 15.0


def test_calibrate_recovers_a_better_config():
    sites = _biased_station_sites()
    candidates = cal.candidate_grid(
        prior_scales={"model_regional": [1.0, 5.0]},   # try trusting the model much more
    )
    best, best_score = cal.calibrate(sites, candidates)
    default_score = cal.score(sites, wf.DEFAULT_CONFIG)
    # The search finds a lower-error config...
    assert best_score["twd_mae"] < default_score["twd_mae"]
    # ...by up-weighting the model that actually matched the truth.
    assert best.priors["model_regional"] > wf.DEFAULT_CONFIG.priors["model_regional"]


def test_candidate_grid_shape_and_defaults():
    grid = cal.candidate_grid(
        prior_scales={"real_station": [0.5, 1.0]},
        distance_decay_km=[10.0, 20.0],
    )
    assert len(grid) == 2 * 2                     # 2 scales x 2 decays
    # Every config keeps the untouched axes at the base value.
    assert all(c.time_decay_seconds == wf.DEFAULT_CONFIG.time_decay_seconds for c in grid)
    assert {round(c.distance_decay_km) for c in grid} == {10, 20}


def test_config_override_changes_weight_but_default_is_unchanged():
    hot = wf.WeightConfig(priors={"gps_estimate": 0.9})
    assert wf.source_weight("gps_estimate", config=hot) == pytest.approx(0.9)
    # Default path untouched by the override.
    assert wf.source_weight("gps_estimate") == pytest.approx(wf.SOURCE_PRIORS["gps_estimate"])
