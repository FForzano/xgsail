"""Leave-one-out calibration of the wind-fusion reliability weights.

The weights in ``WeightConfig`` (per-source priors + decay scales) are picked
by hand; the only honest way to tune them is against ground truth. Real fixed
stations *are* that ground truth: hold one out, predict its wind by fusing
every OTHER source at its location/time, and measure the error. Repeat over
all held-out stations and search ``WeightConfig`` space for the parameters
that minimize it.

This module is the pure evaluation/search core (stdlib only). Assembling real
observations into the ``Site`` shape it consumes — querying ``wind_observations``
and Open-Meteo, holding each station out — is the caller's job; see
``scripts/calibrate_wind_weights.py``.

A ``Site`` is one held-out truth plus the contributions available to predict it:

    {
        "truth_twd": float,                 # the held-out station's direction
        "truth_tws": float | None,          # ...and speed (optional)
        "contributions": [
            {"twd": float, "tws": float, "source_type": str,
             "distance_km": float | None, "dt_seconds": float | None,
             "internal_confidence": float | None},
            ...
        ],
    }
"""

from dataclasses import replace
from itertools import product
from typing import Iterable, Optional

from . import DEFAULT_CONFIG, WeightConfig, source_weight, weighted_wind_mean

Site = dict


def angular_error_deg(predicted_twd: float, true_twd: float) -> float:
    """Smallest absolute difference between two directions, in ``[0, 180]``."""
    return abs((predicted_twd - true_twd + 180.0) % 360.0 - 180.0)


def _fuse_site(site: Site, config: WeightConfig):
    """Fuse a site's contributions under ``config`` → ``(twd, tws, conf)`` or
    ``None`` (nothing usable)."""
    contributions = []
    for c in site.get("contributions", []):
        w = source_weight(
            c["source_type"],
            distance_km=c.get("distance_km"),
            dt_seconds=c.get("dt_seconds"),
            internal_confidence=c.get("internal_confidence"),
            config=config,
        )
        contributions.append((c["twd"], c["tws"], w))
    return weighted_wind_mean(contributions)


def score(sites: "Iterable[Site]", config: WeightConfig = DEFAULT_CONFIG) -> dict:
    """Mean prediction error of ``config`` over the held-out sites:
    ``{twd_mae, tws_mae, n}``. Direction (``twd_mae``, degrees) is the primary
    metric — it's what the fusion is mainly for and what every source reports;
    ``tws_mae`` is over the sites whose truth carries a speed. ``twd_mae`` is
    ``inf`` when no site could be predicted, so an unusable config sorts last."""
    twd_errors = []
    tws_errors = []
    for s in sites:
        fused = _fuse_site(s, config)
        if fused is None:
            continue
        twd, tws, _ = fused
        twd_errors.append(angular_error_deg(twd, s["truth_twd"]))
        if s.get("truth_tws") is not None:
            tws_errors.append(abs(tws - s["truth_tws"]))
    n = len(twd_errors)
    return {
        "twd_mae": (sum(twd_errors) / n) if n else float("inf"),
        "tws_mae": (sum(tws_errors) / len(tws_errors)) if tws_errors else None,
        "n": n,
    }


def calibrate(
    sites: "list[Site]",
    candidates: "Iterable[WeightConfig]",
) -> "tuple[WeightConfig, dict]":
    """Pick the candidate ``WeightConfig`` with the lowest directional error
    over ``sites``. Returns ``(best_config, its_score)``. The caller supplies
    the search space (``candidates``) — e.g. from ``candidate_grid`` — so the
    search stays explicit and reproducible."""
    best_config = DEFAULT_CONFIG
    best_score = {"twd_mae": float("inf"), "tws_mae": None, "n": 0}
    for cfg in candidates:
        s = score(sites, cfg)
        if s["twd_mae"] < best_score["twd_mae"]:
            best_config, best_score = cfg, s
    return best_config, best_score


def candidate_grid(
    base: WeightConfig = DEFAULT_CONFIG,
    *,
    prior_scales: "Optional[dict[str, Iterable[float]]]" = None,
    distance_decay_km: "Optional[Iterable[float]]" = None,
    time_decay_seconds: "Optional[Iterable[float]]" = None,
) -> "list[WeightConfig]":
    """Build a search grid around ``base``. ``prior_scales`` maps a source
    type to the multipliers to try on its base prior; ``distance_decay_km`` /
    ``time_decay_seconds`` are absolute values to try. The Cartesian product of
    everything provided is returned (parameters not given are held at ``base``).

    Kept coarse on purpose — a handful of values per axis over a few axes.
    Wind weighting doesn't need a fine grid, and the product grows fast."""
    prior_scales = prior_scales or {}
    dist_values = list(distance_decay_km) if distance_decay_km is not None else [base.distance_decay_km]
    time_values = list(time_decay_seconds) if time_decay_seconds is not None else [base.time_decay_seconds]

    scaled_types = list(prior_scales.keys())
    scale_axes = [list(prior_scales[t]) for t in scaled_types]

    configs = []
    for scales in product(*scale_axes) if scale_axes else [()]:
        priors = dict(base.priors)
        for t, factor in zip(scaled_types, scales):
            priors[t] = base.priors.get(t, base.default_prior) * factor
        for dist in dist_values:
            for tdecay in time_values:
                configs.append(replace(
                    base, priors=priors, distance_decay_km=dist, time_decay_seconds=tdecay,
                ))
    return configs


__all__ = ["Site", "angular_error_deg", "score", "calibrate", "candidate_grid"]
