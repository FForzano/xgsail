"""Wind direction read off a boat's own tacks and gybes, and the local blend
that folds those readings into a modelled ``true_wind`` series.

A boat sails a beat at about the same angle on both tacks, so the wind comes
from the bisector of the headings before and after a tack; a gybe's bisector
points downwind. That is the one wind measurement a boat without a sensor
makes itself, and it is what catches a station/model direction that is off
by tens of degrees — the failure that files every leg of one tack as a reach.

Each observation is a local, dated point (``{observed_at, lat, lng, twd_deg,
confidence, kind}``). ``blend_observations`` pulls each modelled row toward
the observations near it in space and time, weighted by the shared
``xgsail_windfusion.source_weight("gps_tack", ...)``, so this session's own
tacks and other boats' (``wind_cache.json``'s ``track_observations``) are
weighed identically.
"""

import math
from datetime import datetime, timezone
from statistics import median

import numpy as np

from xgsail_windfusion import blend_direction, source_weight

from .angles import angular_diff, circular_mean
from .models import GpsPoint, Maneuver, ManeuverType
from .straight_lines import _circular_std
from .wind import _to_timestamp

# Steady-course windows either side of a maneuver, in seconds from its
# boundaries. The after-window starts later: the boat is still accelerating
# and settling its angle right out of the turn.
_BEFORE_GAP_S, _AFTER_GAP_S = 5.0, 10.0
_WINDOW_MAX_S = 60.0
_WINDOW_MIN_S = 10.0
_WINDOW_FULL_S = 30.0          # a window this long earns the full window factor
_MIN_WINDOW_POINTS = 5
_MIN_SPEED_KTS = 2.0           # COG is noise below this

_TACK_ANGLE_RANGE = (60.0, 140.0)
_GYBE_ANGLE_RANGE = (20.0, 130.0)

_STEADY_SIGMA_DEG = 8.0        # clean COG on a beat is ~3-5° std; 15° is a wandering course
_CONSISTENCY_SIGMA_DEG = {ManeuverType.TACK: 12.0, ManeuverType.GYBE: 20.0}
_MIN_FOR_CONSISTENCY = 3       # fewer same-kind maneuvers can't form a reference
_UNCHECKED_CONSISTENCY = 0.5
_TYPE_PRIOR = {ManeuverType.TACK: 1.0, ManeuverType.GYBE: 0.5}
_MIN_CONFIDENCE = 0.05

# Seeds: course changes read as tacks, only to unstick a model so far off that
# the classifier saw no tack at all (see ``seed_observations``).
_SEED_PRIOR = 0.5
_SEED_MIN_COUNT = 3
_SEED_MAX_SPREAD_DEG = 10.0

# Pick-first ``cache`` rows carry no fused weight; treat one as a single
# regional model, the typical source it was picked from.
_UNWEIGHTED_ROW_WEIGHT = source_weight("model_regional")


def _gauss(x: float, sigma: float) -> float:
    return math.exp(-0.5 * (x / sigma) ** 2)


def _window(times, lo: float, hi: float):
    """Index mask for ``[lo, hi]``, or ``None`` when too short to trust."""
    if hi - lo < _WINDOW_MIN_S:
        return None
    mask = (times >= lo) & (times <= hi)
    return mask if mask.sum() >= _MIN_WINDOW_POINTS else None


def _candidate(m: Maneuver, kind: ManeuverType, prev_end: float, next_start: float,
               times, headings, speeds, lats, lons):
    """Hard-filtered raw reading for one maneuver read as ``kind``, or ``None``."""
    before = _window(times, max(m.start_time - _WINDOW_MAX_S, prev_end + _AFTER_GAP_S),
                     m.start_time - _BEFORE_GAP_S)
    after = _window(times, m.end_time + _AFTER_GAP_S,
                    min(m.end_time + _WINDOW_MAX_S, next_start - _BEFORE_GAP_S))
    if before is None or after is None:
        return None
    if min(speeds[before].mean(), speeds[after].mean()) < _MIN_SPEED_KTS:
        return None

    h_before, h_after = circular_mean(headings[before]), circular_mean(headings[after])
    angle = abs(float(angular_diff(h_after, h_before)))
    lo, hi = _TACK_ANGLE_RANGE if kind == ManeuverType.TACK else _GYBE_ANGLE_RANGE
    if not lo <= angle <= hi:
        return None

    # The short arc between the two headings holds head-to-wind for a tack and
    # dead downwind for a gybe; both angle ranges stay under 180°, so the
    # circular mean is that arc's bisector.
    bisector = circular_mean(np.array([h_before, h_after]))
    twd = bisector if kind == ManeuverType.TACK else (bisector + 180.0) % 360.0

    std = math.sqrt((_circular_std(headings[before]) ** 2 + _circular_std(headings[after]) ** 2) / 2)
    shortest_s = min(np.ptp(times[before]), np.ptp(times[after]))
    t_mid = (m.start_time + m.end_time) / 2
    return {
        "kind": kind,
        "angle": angle,
        "std": std,
        "shortest_s": float(shortest_s),
        "observed_at": t_mid,
        "lat": float(np.interp(t_mid, times, lats)),
        "lng": float(np.interp(t_mid, times, lons)),
        "twd_deg": round(twd, 1) % 360.0,
    }


def _candidates(gps: "list[GpsPoint]", maneuvers: "list[Maneuver]",
                read_as: "dict[ManeuverType, ManeuverType]") -> "list[dict]":
    """Raw readings for the maneuvers whose type is a key of ``read_as``, each
    read as the mapped kind. Windows are clipped by every neighbouring
    maneuver, whatever its type."""
    if len(gps) < 2 * _MIN_WINDOW_POINTS:
        return []
    times = np.array([p.timestamp for p in gps], dtype=float)
    headings = np.array([p.heading_deg for p in gps], dtype=float)
    speeds = np.array([p.speed_kts for p in gps], dtype=float)
    lats = np.array([p.lat for p in gps], dtype=float)
    lons = np.array([p.lon for p in gps], dtype=float)

    ordered = sorted(maneuvers, key=lambda m: m.start_time)
    out = []
    for i, m in enumerate(ordered):
        if m.maneuver_type not in read_as:
            continue
        prev_end = ordered[i - 1].end_time if i > 0 else -math.inf
        next_start = ordered[i + 1].start_time if i + 1 < len(ordered) else math.inf
        c = _candidate(m, read_as[m.maneuver_type], prev_end, next_start,
                       times, headings, speeds, lats, lons)
        if c is not None:
            out.append(c)
    return out


def observations_from_maneuvers(gps: "list[GpsPoint]", maneuvers: "list[Maneuver]") -> "list[dict]":
    """One wind observation per usable tack/gybe:
    ``{observed_at (unix s), lat, lng, twd_deg, confidence, kind}``.

    ``confidence`` in ``(0, 1]`` is the product of four factors, each a way a
    bisector goes wrong:

    - steadiness — circular std of heading in the two windows. A boat that
      was bearing away, pinching or wandering has no single close-hauled
      heading to bisect;
    - consistency — this maneuver's angle against the session median of the
      same kind. A sailor's tacking angle barely changes between tacks, so an
      outlier is almost always asymmetric (tacked onto a reach, a mark
      rounding, a shift mid-tack), and asymmetry moves the bisector by half
      the difference. With too few maneuvers to form a median the factor is
      a flat penalty: a lone tack can't be cross-checked;
    - type prior — run angles vary far more between gybes than beat angles
      between tacks, and many boats sail one gybe deeper than the other;
    - window length — a window clipped short by a neighbouring maneuver says
      less about where the boat settled."""
    candidates = _candidates(gps, maneuvers, {k: k for k in _TYPE_PRIOR})
    medians = {}
    for kind in _TYPE_PRIOR:
        angles = [c["angle"] for c in candidates if c["kind"] == kind]
        if len(angles) >= _MIN_FOR_CONSISTENCY:
            medians[kind] = median(angles)

    out = []
    for c in candidates:
        kind = c["kind"]
        consistency = (_gauss(c["angle"] - medians[kind], _CONSISTENCY_SIGMA_DEG[kind])
                       if kind in medians else _UNCHECKED_CONSISTENCY)
        window = 0.5 + 0.5 * min(1.0, c["shortest_s"] / _WINDOW_FULL_S)
        confidence = (_TYPE_PRIOR[kind] * _gauss(c["std"], _STEADY_SIGMA_DEG)
                      * consistency * window)
        if confidence < _MIN_CONFIDENCE:
            continue
        out.append({
            "observed_at": c["observed_at"],
            "lat": c["lat"],
            "lng": c["lng"],
            "twd_deg": c["twd_deg"],
            "confidence": round(confidence, 3),
            "kind": kind.value,
        })
    return out


def seed_observations(gps: "list[GpsPoint]", maneuvers: "list[Maneuver]",
                      model_twd_deg: float) -> "list[dict]":
    """Course changes read as tacks, for when the model is so far off that the
    classifier — which decides tack vs course change against that same model
    — recognised no tack at all. A turn of a tacking angle is only a tack if
    it crossed the wind, which the model can't say here; what can is
    agreement: every tack of a beat bisects to the same direction, while
    turns between reaches or around marks scatter. So the seeds count only as
    a group of at least ``_SEED_MIN_COUNT`` whose bisectors agree within
    ``_SEED_MAX_SPREAD_DEG``, resolved to whichever end of their axis is
    nearer the model.

    They are never persisted or shared: the caller uses them to move the axis,
    re-classifies, and keeps only what the classifier then calls a tack."""
    candidates = _candidates(gps, maneuvers, {ManeuverType.COURSE_CHANGE: ManeuverType.TACK})
    if len(candidates) < _SEED_MIN_COUNT:
        return []
    twds = np.array([c["twd_deg"] for c in candidates])
    if _circular_std(twds) > _SEED_MAX_SPREAD_DEG:
        return []
    axis = circular_mean(twds)
    if abs(float(angular_diff(axis, model_twd_deg))) > 90.0:
        axis = (axis + 180.0) % 360.0
    return [{
        "observed_at": c["observed_at"], "lat": c["lat"], "lng": c["lng"],
        "twd_deg": round(axis, 1),
        "confidence": round(_SEED_PRIOR * _gauss(c["std"], _STEADY_SIGMA_DEG), 3),
        "kind": ManeuverType.TACK.value,
    } for c in candidates]


def observations_from_bundle(raw_wind_bundle: "list[dict]") -> "list[dict]":
    """Other boats' observations from ``wind_cache.json``. The same one can be
    attached to several waypoints, hence the dedupe by ``id``; caches written
    before the key existed simply have none."""
    seen, out = set(), []
    for wp in raw_wind_bundle or []:
        for o in wp.get("track_observations") or []:
            if o.get("id") in seen:
                continue
            try:
                obs = {
                    "observed_at": _to_timestamp(o["observed_at"]),
                    "lat": float(o["lat"]), "lng": float(o["lng"]),
                    "twd_deg": float(o["twd_deg"]) % 360.0,
                    "confidence": float(o["confidence"]),
                    "kind": o.get("kind"),
                }
            except (KeyError, TypeError, ValueError):
                continue
            seen.add(o.get("id"))
            out.append(obs)
    return out


def blend_observations(gps: "list[GpsPoint]", true_wind: "list[dict]",
                       observations: "list[dict]") -> "list[dict]":
    """Pull each modelled row's direction toward the observations with
    ``xgsail_windfusion.blend_direction`` — the same local blend the backend
    applies to a single point: the row weighs its own fused source weight,
    each observation ``source_weight("gps_tack", ...)`` decayed by its
    distance from the boat and time from the row. Wind speed is untouched —
    a heading says nothing about it — and ``twa_deg`` follows the new
    direction. ``sensor`` rows are a measurement and are never touched."""
    if not true_wind or not observations:
        return true_wind
    pos_by_t = {p.timestamp: (p.lat, p.lon) for p in gps}
    for r in true_wind:
        if r.get("source") not in ("fusion", "cache") or r.get("twd_deg") is None:
            continue
        pos = pos_by_t.get(r["timestamp"])
        if pos is None:
            continue
        own = r.get("confidence") or _UNWEIGHTED_ROW_WEIGHT
        twd = blend_direction(r["twd_deg"], own, pos[0], pos[1], r["timestamp"], observations)
        r["twd_deg"] = round(twd, 1) % 360.0
        r["twa_deg"] = round(((twd - r["heading_deg"] + 180.0) % 360.0) - 180.0, 1)
    return true_wind


def to_payload(observations: "list[dict]") -> "list[dict]":
    """Observations in the wire shape the backend stores
    (``backend/services/track_wind.py``): ``observed_at`` as ISO-8601 UTC."""
    return [{
        **o,
        "observed_at": datetime.fromtimestamp(o["observed_at"], tz=timezone.utc).isoformat(),
    } for o in observations]
