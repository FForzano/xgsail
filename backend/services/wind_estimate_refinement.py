"""Pluggable strategies for turning raw wind observations into (or refining)
the determined estimate for a grid cell/time bucket — see
``db/models/wind.py::WindEstimateORM`` and ``services/wind_estimates.py``
for the grid itself.

Two strategies ship:

- ``first_write_wins`` (placeholder): store the first observation, ignore
  every later one.
- ``weighted_merge`` (default): blend the existing cell estimate with the
  new observation using the shared ``xgsail_windfusion`` weighting — the
  *same* vector math and reliability priors the worker uses per-session
  (``workers/process_upload/processing/wind_estimation.py``), so the
  accumulated grid and the per-session estimate stay coherent.
"""

from typing import Callable, Optional

from xgsail_windfusion import source_weight, weighted_wind_mean

# (existing estimate dict or None, new raw observation) -> new estimate dict
# to write. ``observation`` shape: {twd_deg, tws_kts, gust_kts, type: str,
# **whatever else identifies it — session_id, station_id, model, observed_at}.
WindEstimateRefiner = Callable[[Optional[dict], dict], dict]

# Non-wind observation keys become the recorded ``source`` provenance entry.
_WIND_KEYS = ("twd_deg", "tws_kts", "gust_kts")


def _source_entry(observation: dict) -> dict:
    """The provenance record for one observation — everything that isn't the
    wind values themselves (type, session_id, observed_at, ...)."""
    return {k: v for k, v in observation.items() if k not in _WIND_KEYS}


def first_write_wins(existing: Optional[dict], observation: dict) -> dict:
    """Placeholder: if no estimate exists yet for this cell/bucket, store
    the observation as-is; if one already exists, leave it untouched (return
    it unchanged). No blending, no source-priority weighting."""
    if existing is not None:
        return existing
    return {
        "twd_deg": observation.get("twd_deg"),
        "tws_kts": observation.get("tws_kts"),
        "gust_kts": observation.get("gust_kts"),
        "confidence": None,
        "sources": [_source_entry(observation)],
    }


def _weighted_scalar(pairs: "list[tuple[float, float]]") -> Optional[float]:
    """Weighted mean of ``(value, weight)`` pairs (for gust, a plain scalar);
    ``None`` if there's nothing to average."""
    num = sum(v * w for v, w in pairs)
    den = sum(w for _, w in pairs)
    return (num / den) if den > 0 else None


def weighted_merge(existing: Optional[dict], observation: dict) -> dict:
    """Blend the existing cell estimate with the new observation as a
    reliability-weighted vector mean.

    The existing estimate re-enters as one contribution weighted by its own
    accumulated ``confidence`` (which *is* the total weight that produced it —
    so evidence compounds across refinements); the new observation is weighted
    by ``source_weight`` for its type. Direction/speed fuse in vector space;
    gust is a weighted scalar mean; ``sources`` accumulates provenance; the
    new ``confidence`` is the fused total weight.

    Falls back to keeping the existing row (or writing the observation raw,
    like ``first_write_wins``) when there's nothing fusable — e.g. an
    observation with no speed."""
    obs_type = observation.get("type") or "onboard_sensor"
    obs_weight = source_weight(obs_type)

    contributions = []          # (twd, tws, weight) for the vector mean
    gusts = []                  # (gust, weight) for the scalar mean
    sources = []

    if existing is not None:
        sources.extend(existing.get("sources") or [])
        # A pre-``weighted_merge`` row (e.g. from first_write_wins) has no
        # confidence yet — treat it as a single unit of evidence.
        existing_weight = existing.get("confidence") or 1.0
        if existing.get("twd_deg") is not None and existing.get("tws_kts") is not None:
            contributions.append((existing["twd_deg"], existing["tws_kts"], existing_weight))
        if existing.get("gust_kts") is not None:
            gusts.append((existing["gust_kts"], existing_weight))

    sources.append(_source_entry(observation))
    if observation.get("twd_deg") is not None and observation.get("tws_kts") is not None:
        contributions.append((observation["twd_deg"], observation["tws_kts"], obs_weight))
    if observation.get("gust_kts") is not None:
        gusts.append((observation["gust_kts"], obs_weight))

    fused = weighted_wind_mean(contributions)
    if fused is None:
        # Nothing to fuse (no usable speed anywhere). Keep the existing wind
        # values if we have them, otherwise store the observation's as-is —
        # but always record that this observation was seen.
        base = existing if existing is not None else observation
        return {
            "twd_deg": base.get("twd_deg"),
            "tws_kts": base.get("tws_kts"),
            "gust_kts": base.get("gust_kts"),
            "confidence": existing.get("confidence") if existing is not None else None,
            "sources": sources,
        }

    twd, tws, confidence = fused
    return {
        "twd_deg": twd,
        "tws_kts": tws,
        "gust_kts": _weighted_scalar(gusts),
        "confidence": confidence,
        "sources": sources,
    }


STRATEGIES: dict[str, WindEstimateRefiner] = {
    "first_write_wins": first_write_wins,
    "weighted_merge": weighted_merge,
}

# Change this (and redeploy the backend) to switch strategies.
ACTIVE_STRATEGY = "weighted_merge"


def refine(existing: Optional[dict], observation: dict) -> dict:
    return STRATEGIES[ACTIVE_STRATEGY](existing, observation)
