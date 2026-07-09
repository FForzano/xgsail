"""Pluggable strategies for turning raw wind observations into (or refining)
the determined estimate for a grid cell/time bucket — see
``db/models/wind.py::WindEstimateORM`` and ``services/wind_estimates.py``
for the grid itself.

This is deliberately a skeleton: the default strategy below does the
simplest possible thing (write once, never touch again) and is not meant to
be the real answer — write your own combination/weighting logic (e.g. by
source-type confidence, recency, distance from cell center) and register it
in ``STRATEGIES``.
"""

from typing import Callable, Optional

# (existing estimate dict or None, new raw observation) -> new estimate dict
# to write. ``observation`` shape: {twd_deg, tws_kts, gust_kts, source: str,
# **whatever else identifies it — session_id, station_id, model, observed_at}.
WindEstimateRefiner = Callable[[Optional[dict], dict], dict]


def first_write_wins(existing: Optional[dict], observation: dict) -> dict:
    """Placeholder: if no estimate exists yet for this cell/bucket, store
    the observation as-is; if one already exists, leave it untouched (return
    it unchanged). No blending, no source-priority weighting — replace this
    with your own v1."""
    if existing is not None:
        return existing
    source = {k: v for k, v in observation.items()
             if k not in ("twd_deg", "tws_kts", "gust_kts")}
    return {
        "twd_deg": observation.get("twd_deg"),
        "tws_kts": observation.get("tws_kts"),
        "gust_kts": observation.get("gust_kts"),
        "confidence": None,
        "sources": [source],
    }


STRATEGIES: dict[str, WindEstimateRefiner] = {
    "first_write_wins": first_write_wins,
}

# Change this (and redeploy the backend) to switch strategies.
ACTIVE_STRATEGY = "first_write_wins"


def refine(existing: Optional[dict], observation: dict) -> dict:
    return STRATEGIES[ACTIVE_STRATEGY](existing, observation)
