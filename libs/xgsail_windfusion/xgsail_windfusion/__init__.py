"""Wind-vector fusion + source-reliability weighting — the single source of
truth shared by the process_upload worker (per-session ``true_wind``
estimate) and the backend (grid-cell refinement). If these two seams used
different blend math or different reliability weights, the per-session
estimate and the accumulated grid would disagree — a correctness bug, not
just duplication. Hence one package, imported by both images.

Two ideas, both borrowed from how a Kalman filter fuses sensors:

1. **Fuse in vector space, never average degrees.** A wind reading
   ``(twd, tws)`` becomes an east/north vector ``(u, v)``; contributions are
   averaged there and recombined. Averaging 350° and 10° as numbers gives
   180° (wrong); as vectors it gives ~0° (right). Working in ``(u, v)`` also
   couples speed and direction the way physics does — a strong reading pulls
   the mean direction toward itself.

2. **Reliability is a weight (inverse variance).** Each contribution carries
   a weight; the fused value is the weighted vector mean and the total weight
   is a confidence signal. ``source_weight`` builds that weight from a
   per-source-type prior times spatial and temporal decay times the source's
   own confidence — the one place reliability policy lives.

``waypoint`` builds on both to fuse a whole ``wind_cache.json`` waypoint at
one instant — the per-session estimate and the backend's live point value.

Dependency-free on purpose (stdlib ``math`` only) so it can live in the
numpy-free backend image as well as the worker.
"""

import math
from dataclasses import dataclass, field

# --- reliability policy (starting values; calibrate with the leave-one-out
# harness in ``xgsail_windfusion.calibration``) --------------------------

# Base reliability per source type, before any spatial/temporal decay.
# Onboard sensor and a real fixed station are the most trustworthy; regional
# NWP models beat global ones; a grid estimate is prior knowledge; a wind
# direction guessed from a GPS tack pattern is the weakest.
SOURCE_PRIORS: "dict[str, float]" = {
    # Up to 4 Open-Meteo models can contribute at once, each queried at the
    # waypoint with no spatial decay, so their *summed* weight (~1.9-2.4 with
    # a grid estimate) otherwise drowns out a real station even directly on
    # top of it, or the boat's own instrument. Both are weighed near/above
    # that summed model contribution so a healthy nearby station — and the
    # boat's own sensor, kept above it — dominate that consensus rather than
    # being outvoted by it.
    "onboard_sensor": 2.2,
    "real_station": 2.0,
    "model_regional": 0.6,   # Open-Meteo icon_d2 / icon_eu
    "model_global": 0.35,    # Open-Meteo gfs_seamless / ecmwf_ifs025
    "grid_estimate": 0.5,
    "gps_estimate": 0.2,
    # Wind direction bisected from one tack/gybe (``process_upload/processing/
    # tack_wind.py``), already scaled by that maneuver's own confidence. Above
    # the sensor prior because it is weighed against a row's *summed* model
    # weight (~1.9 for four Open-Meteo models sharing one bias), and it only
    # holds that strength within a couple of km and ~half an hour — see the
    # overrides below.
    "gps_tack": 2.0,
}
_DEFAULT_PRIOR = 0.1  # unknown source type — trusted little, never zero

# Characteristic scales for the exponential decays. A contribution loses a
# factor 1/e of its weight per this much distance / time offset.
DISTANCE_DECAY_KM = 15.0
# Per-source override of ``DISTANCE_DECAY_KM``. A tack bisector describes the
# wind where the boat was, not a weather system: its influence should end
# around the next headland, not 15 km away.
DISTANCE_DECAY_KM_BY_SOURCE: "dict[str, float]" = {"gps_tack": 2.0}
TIME_DECAY_SECONDS = 30.0 * 60.0  # 30 minutes
# Per-source override of ``TIME_DECAY_SECONDS``. Coastal/thermal wind shifts
# over tens of minutes, so a tack bisector is trusted most at its own moment
# and fades within about half an hour either side (weight 1/e at 15 min,
# ~0.14 at 30 min).
TIME_DECAY_SECONDS_BY_SOURCE: "dict[str, float]" = {"gps_tack": 15.0 * 60.0}


@dataclass(frozen=True)
class WeightConfig:
    """A full parameterization of the reliability policy — the priors and
    decay scales ``source_weight`` uses. Defaults reproduce the module
    constants exactly, so ``source_weight(...)`` with no ``config`` is
    unchanged. Calibration (``calibration.calibrate``) searches over instances
    of this to fit the weighting to real held-out station data."""
    priors: "dict[str, float]" = field(default_factory=lambda: dict(SOURCE_PRIORS))
    default_prior: float = _DEFAULT_PRIOR
    distance_decay_km: float = DISTANCE_DECAY_KM
    distance_decay_km_by_source: "dict[str, float]" = field(
        default_factory=lambda: dict(DISTANCE_DECAY_KM_BY_SOURCE))
    time_decay_seconds: float = TIME_DECAY_SECONDS
    time_decay_seconds_by_source: "dict[str, float]" = field(
        default_factory=lambda: dict(TIME_DECAY_SECONDS_BY_SOURCE))


DEFAULT_CONFIG = WeightConfig()


def to_uv(twd_deg: float, tws_kts: float) -> "tuple[float, float]":
    """Wind direction/speed → east/north vector ``(u, v)``. ``twd_deg`` follows
    the same convention as the rest of the pipeline (degrees, 0 = North)."""
    r = math.radians(twd_deg)
    return tws_kts * math.sin(r), tws_kts * math.cos(r)


def from_uv(u: float, v: float) -> "tuple[float, float]":
    """East/north vector ``(u, v)`` → ``(twd_deg, tws_kts)``. Inverse of
    ``to_uv``; direction normalized to ``[0, 360)``."""
    tws = math.hypot(u, v)
    twd = (math.degrees(math.atan2(u, v)) + 360.0) % 360.0
    return twd, tws


def source_weight(
    source_type: str,
    *,
    distance_km: "float | None" = None,
    dt_seconds: "float | None" = None,
    internal_confidence: "float | None" = None,
    config: "WeightConfig | None" = None,
) -> float:
    """Reliability weight for one contribution: a per-type prior, decayed
    exponentially by how far the source is from the point of interest
    (``distance_km``) and how far its observation time is from the target
    time (``dt_seconds``), and scaled by the source's own confidence if it
    reports one. Monotonically non-increasing in ``distance_km`` and
    ``|dt_seconds|``. Any argument left ``None`` is simply not applied (e.g.
    Open-Meteo is queried at the point, so it has no spatial offset).

    ``config`` overrides the priors/decay scales (used by calibration); it
    defaults to the shipped policy (``DEFAULT_CONFIG``)."""
    cfg = config or DEFAULT_CONFIG
    w = cfg.priors.get(source_type, cfg.default_prior)
    if distance_km is not None:
        decay_km = cfg.distance_decay_km_by_source.get(source_type, cfg.distance_decay_km)
        w *= math.exp(-max(distance_km, 0.0) / decay_km)
    if dt_seconds is not None:
        decay_s = cfg.time_decay_seconds_by_source.get(source_type, cfg.time_decay_seconds)
        w *= math.exp(-abs(dt_seconds) / decay_s)
    if internal_confidence is not None:
        w *= max(internal_confidence, 0.0)
    return w


def weighted_wind_mean(
    contributions: "list[tuple[float, float, float]]",
) -> "tuple[float, float, float] | None":
    """Fuse ``(twd_deg, tws_kts, weight)`` contributions into one
    ``(twd_deg, tws_kts, confidence)``, as a weighted mean in ``(u, v)`` space.

    ``confidence`` is the total weight that actually contributed — higher
    means more, closer, or more-trusted sources agreed. It is NOT normalized
    to ``[0, 1]`` (that scaling is deferred to the leave-one-out calibration
    in Fase 4). Note it does not yet penalize disagreement: two sources
    pointing opposite ways cancel in the mean but still report high total
    weight — an agreement-aware confidence is a later refinement.

    Returns ``None`` if nothing usable was passed (empty, or every weight
    non-positive, or missing values)."""
    sum_u = sum_v = sum_w = 0.0
    for twd, tws, w in contributions:
        if twd is None or tws is None or w is None or w <= 0.0:
            continue
        u, v = to_uv(twd, tws)
        sum_u += w * u
        sum_v += w * v
        sum_w += w
    if sum_w <= 0.0:
        return None
    twd, tws = from_uv(sum_u / sum_w, sum_v / sum_w)
    return twd, tws, sum_w


# Imported last: ``waypoint`` builds on the weighting defined above.
from .waypoint import (  # noqa: E402
    MODEL_SOURCE_TYPE,
    FusedWind,
    WindSource,
    blend_direction,
    fuse_sources,
    fuse_waypoint,
    haversine_km,
    prepare_sources,
    station_groups,
    to_epoch,
)

__all__ = [
    "MODEL_SOURCE_TYPE",
    "FusedWind",
    "WindSource",
    "blend_direction",
    "fuse_sources",
    "fuse_waypoint",
    "haversine_km",
    "prepare_sources",
    "station_groups",
    "to_epoch",
    "SOURCE_PRIORS",
    "DISTANCE_DECAY_KM",
    "DISTANCE_DECAY_KM_BY_SOURCE",
    "TIME_DECAY_SECONDS",
    "TIME_DECAY_SECONDS_BY_SOURCE",
    "WeightConfig",
    "DEFAULT_CONFIG",
    "to_uv",
    "from_uv",
    "source_weight",
    "weighted_wind_mean",
]
