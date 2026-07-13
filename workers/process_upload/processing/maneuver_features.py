"""Configurable statistical features for a maneuver candidate — the Stage 1
"statistics about the course change" half of the two-stage detection pipeline.

Each feature is a small function with the ``FeatureExtractor`` signature,
registered in ``FEATURE_EXTRACTORS``. ``ENABLED_FEATURES`` selects which ones
are computed (default: all) — a module constant, same idiom as
``wind_estimation.ACTIVE_STRATEGY`` (change it and rebuild the worker image;
not env-configurable). ``extract_features`` runs the enabled extractors over a
``FeatureContext`` and returns a plain dict.

The resulting dict is what:
  * today's geometric classifier reads (``rel_before``/``rel_after``), and
  * a future ML classifier will consume as its feature vector, and
  * gets persisted on ``session_maneuvers.features`` to build a training set.

A few CORE keys (``rel_before``, ``rel_after``, ``avg_abs_rel``,
``had_wind_axis``) are ALWAYS emitted regardless of ``ENABLED_FEATURES`` because
the active classifier depends on them — disabling them must not break
classification. ``FEATURE_SCHEMA_VERSION`` is stored alongside the dataset so a
future model knows which schema produced a given row.

Some extractors (``speed_loss``, ``speed_min_during``, ``delta_heading``,
``crossing_duration``, ``time_to_speed_recovery``) intentionally duplicate a
value already stored as its own ``Maneuver``/``session_maneuvers`` column
(``speed_loss_kts``, ``speed_min_kts``, ``heading_change_deg``,
``duration_sec``, ``recovery_time_sec``). This is deliberate, not an oversight
to clean up: the columns are the stable, typed contract the frontend/API read
and may evolve independently (renamed, reshaped, deprecated); ``features`` is
meant to stay a SELF-CONTAINED training vector — a future export/training
script should be able to read one JSON blob per maneuver and get the full
feature set, without joining back to the columns it happened to be persisted
alongside.
"""

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from .angles import angular_diff
from .models import GpsPoint, ImuReading
from .vmg import compute_vmg

# Bump when the meaning/set of features changes, so persisted training rows
# stay interpretable across schema evolution.
FEATURE_SCHEMA_VERSION = 1

# Length of the pre-event and post-event windows used by the *_pre/*_post
# features (seconds ~ samples at 1 Hz).
PRE_POST_WINDOW_SEC = 15.0

# Recovery target used by time_to_speed_recovery (mirrors maneuvers.py).
SPEED_RECOVERY_THRESHOLD = 0.9
MAX_RECOVERY_WINDOW_SEC = 60.0


@dataclass
class FeatureContext:
    """Everything a feature extractor might need about one candidate and its
    surroundings. Built by ``maneuvers._detect_candidates`` once per candidate.

    ``true_wind`` is the per-point series from ``wind_estimation.estimate`` (rows
    with ``timestamp``/``twd_deg``); ``None``/empty when no wind is available, in
    which case TWA/VMG-based features degrade to ``None``.
    """
    gps: "list[GpsPoint]"
    imu: "Optional[list[ImuReading]]"
    true_wind: "Optional[list[dict]]"
    axis_deg: float
    had_wind_axis: bool
    # Event boundaries + geometry (already computed by the detector).
    t_start: float
    t_end: float
    heading_before: float
    heading_after: float
    speed_before_kts: float
    speed_min_kts: float
    speed_after_kts: float
    recovery_time_sec: float
    # Signed angle of the pre/post heading to the wind axis (classifier inputs).
    rel_before: float
    rel_after: float
    # Max |heel| during the event, from IMU (None without IMU data). Lives only
    # here/in `features` — it characterizes the maneuver itself (unlike
    # position/timing, which stay as their own Maneuver columns).
    max_heel_deg: "Optional[float]" = None
    window_sec: float = PRE_POST_WINDOW_SEC
    # Lazily-built (times, sin, cos) arrays for circular TWD interpolation.
    _twd_arrays: object = field(default=None, repr=False, compare=False)


FeatureExtractor = Callable[[FeatureContext], "Optional[float]"]


# --------------------------------------------------------------------------- #
# Windowing / interpolation helpers
# --------------------------------------------------------------------------- #

def _window(gps: "list[GpsPoint]", t0: float, t1: float) -> "list[GpsPoint]":
    """GPS points with ``t0 <= timestamp <= t1``."""
    return [p for p in gps if t0 <= p.timestamp <= t1]


def _pre(ctx: FeatureContext) -> "list[GpsPoint]":
    return _window(ctx.gps, ctx.t_start - ctx.window_sec, ctx.t_start)


def _post(ctx: FeatureContext) -> "list[GpsPoint]":
    return _window(ctx.gps, ctx.t_end, ctx.t_end + ctx.window_sec)


def _during(ctx: FeatureContext) -> "list[GpsPoint]":
    return _window(ctx.gps, ctx.t_start, ctx.t_end)


def _twd_arrays(ctx: FeatureContext):
    """Prepared (times, sin, cos) arrays for circular interpolation of the true
    wind direction, or ``None`` when there's no usable wind series. Cached on
    the context so repeated TWA/VMG extractors don't rebuild it."""
    if ctx._twd_arrays is not None:
        return ctx._twd_arrays if ctx._twd_arrays != () else None
    rows = ctx.true_wind or []
    triples = []
    for r in rows:
        t, twd = r.get("timestamp"), r.get("twd_deg")
        if t is None or twd is None:
            continue
        triples.append((float(t), float(twd)))
    if not triples:
        ctx._twd_arrays = ()  # sentinel: "computed, empty"
        return None
    triples.sort(key=lambda x: x[0])
    times = np.array([x[0] for x in triples])
    sin_a = np.array([math.sin(math.radians(x[1])) for x in triples])
    cos_a = np.array([math.cos(math.radians(x[1])) for x in triples])
    ctx._twd_arrays = (times, sin_a, cos_a)
    return ctx._twd_arrays


def _twd_at(ctx: FeatureContext, t: float) -> "Optional[float]":
    arrays = _twd_arrays(ctx)
    if arrays is None:
        return None
    times, sin_a, cos_a = arrays
    if t < times[0] or t > times[-1]:
        return None
    s = float(np.interp(t, times, sin_a))
    c = float(np.interp(t, times, cos_a))
    return (math.degrees(math.atan2(s, c)) + 360.0) % 360.0


def _twa_at(ctx: FeatureContext, p: GpsPoint) -> "Optional[float]":
    """Signed true wind angle (heading relative to TWD) at a GPS point."""
    twd = _twd_at(ctx, p.timestamp)
    if twd is None:
        return None
    return float(angular_diff(p.heading_deg, twd))


def _mean(values: "list[float]") -> "Optional[float]":
    vals = [v for v in values if v is not None]
    return float(np.mean(vals)) if vals else None


# --------------------------------------------------------------------------- #
# Feature extractors
# --------------------------------------------------------------------------- #

def _rel_before(ctx: FeatureContext) -> float:
    return ctx.rel_before


def _rel_after(ctx: FeatureContext) -> float:
    return ctx.rel_after


def _avg_abs_rel(ctx: FeatureContext) -> float:
    return (abs(ctx.rel_before) + abs(ctx.rel_after)) / 2.0


def _had_wind_axis(ctx: FeatureContext) -> float:
    return 1.0 if ctx.had_wind_axis else 0.0


def _twa_pre_mean(ctx: FeatureContext) -> "Optional[float]":
    return _mean([_twa_at(ctx, p) for p in _pre(ctx)])


def _twa_post_mean(ctx: FeatureContext) -> "Optional[float]":
    return _mean([_twa_at(ctx, p) for p in _post(ctx)])


def _twa_min_abs(ctx: FeatureContext) -> "Optional[float]":
    twas = [abs(v) for p in _during(ctx) if (v := _twa_at(ctx, p)) is not None]
    return float(min(twas)) if twas else None


def _twa_sign_change(ctx: FeatureContext) -> "Optional[float]":
    """1.0 if the boat crossed the wind (TWA changes sign pre→post), else 0.0."""
    pre = _twa_pre_mean(ctx)
    post = _twa_post_mean(ctx)
    if pre is None or post is None:
        return None
    return 1.0 if (pre >= 0) != (post >= 0) else 0.0


def _delta_heading(ctx: FeatureContext) -> float:
    return float(angular_diff(ctx.heading_after, ctx.heading_before))


def _max_heel_deg(ctx: FeatureContext) -> "Optional[float]":
    """Max |heel| during the event (from IMU); None without IMU data. The only
    home for this value — it does NOT also live as a ``Maneuver`` column
    (moved here deliberately: heel characterizes the maneuver, not a specific
    occurrence's position/timing)."""
    return ctx.max_heel_deg


def _delta_cog(ctx: FeatureContext) -> "Optional[float]":
    """Change in course-over-ground between the last pre-window point and the
    first post-window point (GPS-course based, independent of the smoothed
    boundary headings)."""
    pre, post = _pre(ctx), _post(ctx)
    if not pre or not post:
        return None
    return float(angular_diff(post[0].heading_deg, pre[-1].heading_deg))


def _max_abs_turn_rate(ctx: FeatureContext) -> "Optional[float]":
    during = _during(ctx)
    if len(during) < 2:
        return None
    rates = []
    for a, b in zip(during, during[1:]):
        dt = b.timestamp - a.timestamp
        if dt > 0:
            rates.append(abs(float(angular_diff(b.heading_deg, a.heading_deg)) / dt))
    return float(max(rates)) if rates else None


def _speed_pre_mean(ctx: FeatureContext) -> "Optional[float]":
    return _mean([p.speed_kts for p in _pre(ctx)])


def _speed_min_during(ctx: FeatureContext) -> float:
    return ctx.speed_min_kts


def _speed_post_mean(ctx: FeatureContext) -> "Optional[float]":
    return _mean([p.speed_kts for p in _post(ctx)])


def _speed_loss(ctx: FeatureContext) -> float:
    return ctx.speed_before_kts - ctx.speed_min_kts


def _vmg_mean(ctx: FeatureContext, points: "list[GpsPoint]") -> "Optional[float]":
    vals = []
    for p in points:
        twd = _twd_at(ctx, p.timestamp)
        if twd is None:
            continue
        vals.append(compute_vmg(p.speed_kts, p.heading_deg, twd))
    return _mean(vals)


def _vmg_pre_mean(ctx: FeatureContext) -> "Optional[float]":
    return _vmg_mean(ctx, _pre(ctx))


def _vmg_post_mean(ctx: FeatureContext) -> "Optional[float]":
    return _vmg_mean(ctx, _post(ctx))


def _vmg_loss(ctx: FeatureContext) -> "Optional[float]":
    pre, post = _vmg_pre_mean(ctx), _vmg_post_mean(ctx)
    if pre is None or post is None:
        return None
    return pre - post


def _crossing_duration(ctx: FeatureContext) -> float:
    return ctx.t_end - ctx.t_start


def _time_to_speed_recovery(ctx: FeatureContext) -> float:
    return ctx.recovery_time_sec


def _post_event_stability(ctx: FeatureContext) -> "Optional[float]":
    """Circular std-dev of heading over the post-event window — low means the
    boat settled quickly onto a straight course after the maneuver."""
    post = _post(ctx)
    if len(post) < 2:
        return None
    rad = np.radians([p.heading_deg for p in post])
    r = math.hypot(float(np.mean(np.sin(rad))), float(np.mean(np.cos(rad))))
    r = min(1.0, max(1e-9, r))
    return float(math.degrees(math.sqrt(-2.0 * math.log(r))))


# Registry — add a feature by writing an extractor and registering it here.
FEATURE_EXTRACTORS: "dict[str, FeatureExtractor]" = {
    "rel_before": _rel_before,
    "rel_after": _rel_after,
    "avg_abs_rel": _avg_abs_rel,
    "had_wind_axis": _had_wind_axis,
    "twa_pre_mean": _twa_pre_mean,
    "twa_post_mean": _twa_post_mean,
    "twa_min_abs": _twa_min_abs,
    "twa_sign_change": _twa_sign_change,
    "delta_heading": _delta_heading,
    "delta_cog": _delta_cog,
    "max_abs_turn_rate": _max_abs_turn_rate,
    "max_heel_deg": _max_heel_deg,
    "speed_pre_mean": _speed_pre_mean,
    "speed_min_during": _speed_min_during,
    "speed_post_mean": _speed_post_mean,
    "speed_loss": _speed_loss,
    "vmg_pre_mean": _vmg_pre_mean,
    "vmg_post_mean": _vmg_post_mean,
    "vmg_loss": _vmg_loss,
    "crossing_duration": _crossing_duration,
    "time_to_speed_recovery": _time_to_speed_recovery,
    "post_event_stability": _post_event_stability,
}

# Core features the active classifier depends on — always emitted, even if a
# custom ENABLED_FEATURES omits them.
CORE_FEATURES = ("rel_before", "rel_after", "avg_abs_rel", "had_wind_axis")

# Which features to compute. Default: all registered. Change this constant to
# experiment (not env-configurable — rebuild the worker image).
ENABLED_FEATURES: "tuple[str, ...]" = tuple(FEATURE_EXTRACTORS.keys())


def extract_features(
    ctx: FeatureContext,
    enabled: "tuple[str, ...]" = ENABLED_FEATURES,
) -> dict:
    """Run the enabled extractors (plus the always-on CORE features) over
    ``ctx`` and return a ``{name: value}`` dict. Extractors that lack the data
    they need return ``None``; those keys are still present so the training-set
    schema is stable."""
    names = list(dict.fromkeys(CORE_FEATURES + tuple(enabled)))  # dedupe, keep order
    out = {name: FEATURE_EXTRACTORS[name](ctx) for name in names if name in FEATURE_EXTRACTORS}
    out["_schema_version"] = FEATURE_SCHEMA_VERSION
    return out
