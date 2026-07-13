"""Maneuver detection — two-stage pipeline.

Stage 1 (this module): ``_detect_candidates`` finds significant course changes
(debounced tack-side transitions), refines their boundaries, computes the
type-independent performance metrics, and extracts a configurable statistical
feature vector (see ``maneuver_features``). Stage 2
(``maneuver_classification``): a pluggable classifier maps each candidate to a
``ManeuverType`` — or to ``None`` (false alarm) so the candidate is dropped.

``detect_maneuvers`` is the unchanged public entry point that composes the two
stages; today's active ``geometric`` classifier reproduces the previous
tack/gybe behavior exactly.
"""

import numpy as np

from .angles import angular_diff as _angular_diff
from .angles import circular_mean as _circular_mean
from .maneuver_classification import classify_maneuver
from .maneuver_features import FeatureContext, extract_features
from .models import GpsPoint, ImuReading, Maneuver, ManeuverCandidate, ManeuverType


# Detection thresholds
MAX_MANEUVER_DURATION_SEC = 30  # max time for heading change
MIN_BOAT_SPEED_KTS = 1.5  # ignore turns while nearly stopped
SPEED_RECOVERY_THRESHOLD = 0.9  # 90% of entry speed
MAX_RECOVERY_WINDOW_SEC = 60
TURN_RATE_THRESHOLD = 3.0  # deg/sec to detect turn
TURN_WINDOW_EXTEND_SEC = 5  # extend window before/after rapid portion
MIN_MANEUVER_SPACING_SEC = 20  # minimum time between maneuvers to avoid duplicates
# backend/services/maneuver_reconciliation.py::OVERLAP_TOLERANCE_SEC (15s)
# must stay strictly below this — see that module's docstring.
HEADING_SMOOTH_WINDOW = 5  # samples, circular moving average before detection
HOLD_WINDOW_SEC = 12  # min dwell time on a side for it to count as a real tack
# A genuine tack/gybe is a real rotation, not just a slow drift that happens
# to cross the wind-axis boundary the side-debounce logic tracks (e.g. a
# zero-duration/zero-change "maneuver" is a detection glitch, not a real
# one). Gybes have no dead zone the way tacking does — a boat already
# sailing deep can gybe with a fairly modest heading change — so this floor
# is only high enough to reject the degenerate cases, not to demand a wide
# rotation.
MIN_TACK_HEADING_CHANGE_DEG = 40
MIN_GYBE_HEADING_CHANGE_DEG = 20


def detect_maneuvers(
    gps: list[GpsPoint],
    imu: list[ImuReading] | None = None,
    twd_deg: float | None = None,
    true_wind: list[dict] | None = None,
) -> list[Maneuver]:
    """Detect tacks and gybes from heading changes (public entry point).

    Composes the two stages: Stage 1 (``_detect_candidates``) produces the
    significant-course-change candidates with their metrics + features; Stage 2
    (``classify_maneuver``) labels each one (or rejects it as a false alarm).
    The per-type minimum-heading-change filter and the inter-maneuver spacing
    gate stay HERE, interleaved with classification and only advancing
    ``last_maneuver_end`` on a real append — preserving the exact ordering of
    the previous single-loop implementation.

    ``true_wind`` (per-point series) only feeds the TWA/VMG-based *features*;
    it does not affect which maneuvers are detected or how they're classified,
    so the result is identical whether or not it is provided.
    """
    candidates = _detect_candidates(gps, imu, twd_deg, true_wind)

    maneuvers: list[Maneuver] = []
    last_maneuver_end = -999999
    for cand in candidates:
        # Inter-maneuver spacing: same semantics as before — measured against
        # the end of the last ACCEPTED maneuver, so candidates dropped below
        # never reset the baseline.
        if cand.start_time < last_maneuver_end + MIN_MANEUVER_SPACING_SEC:
            continue

        maneuver_type = classify_maneuver(cand)
        if maneuver_type is None:
            continue  # false alarm — not a real maneuver

        # LABEL-COLLECTION HOOK (future): here is where a "corrected label"
        # from the user, or a training-data sink, would attach — cand.features
        # is fully populated at this point.

        maneuver = _finalize(cand, maneuver_type)
        if maneuver is None:
            continue  # below the per-type minimum heading change

        maneuvers.append(maneuver)
        last_maneuver_end = cand.end_time

    return maneuvers


def _detect_candidates(
    gps: list[GpsPoint],
    imu: list[ImuReading] | None,
    twd_deg: float | None,
    true_wind: list[dict] | None = None,
) -> list[ManeuverCandidate]:
    """Stage 1: find significant course-change candidates and describe them.

    A candidate is a genuine tack-side change (port/starboard relative to the
    wind axis), not just any rapid heading change — a tactical heading wiggle
    or an aborted/failed maneuver that rounds back never really settles onto
    the new side, so neither should count. This is enforced structurally: the
    whole per-sample side sequence is first debounced (`_debounced_sides`),
    absorbing any side run shorter than `HOLD_WINDOW_SEC` into its
    predecessor, so every remaining transition is guaranteed to have *both* a
    settled "before" and a settled "after" side. Each surviving transition is
    refined to its precise start/end (where the heading actually starts/stops
    turning) and gets its type-independent metrics + feature vector computed.
    Without real wind data (`twd_deg`), falls back to a synthetic axis (the
    track's circular-mean heading) for the same side test, at reduced
    confidence.

    Applies only the classification-INDEPENDENT gates (duration, entry speed).
    The spacing and per-type min-heading-change gates are applied by the caller
    (`detect_maneuvers`), interleaved with classification, to preserve the
    original ordering.
    """
    if len(gps) < 20:
        return []

    times, raw_headings, headings, gps_speeds, gps_lats, gps_lons = _detection_arrays(gps)
    axis_deg, had_wind_axis = resolve_wind_axis(raw_headings, twd_deg)

    # Window used only to refine each candidate's precise start/end once a
    # real transition has already been located (see WINDOW_SIZE usage below).
    WINDOW_SIZE = 25  # samples (seconds at 1Hz)

    sides = np.array([_tack_side(h, axis_deg) for h in headings])
    sides = _debounced_sides(sides, times, HOLD_WINDOW_SEC)
    transitions = np.where(np.diff(sides) != 0)[0]

    candidates: list[ManeuverCandidate] = []

    for pivot in transitions:
        # Refine the actual turn boundaries around the debounced transition:
        # scan backward for where the rapid heading change begins, forward
        # for where it stabilizes on the new side (same rate-of-turn logic
        # as before, just anchored on a confirmed real transition). This
        # boundary search is specific to "found a transition, where exactly
        # does it start/end" — a manual maneuver skips it entirely since the
        # user already gives exact boundaries (see compute_manual_maneuver).
        start_idx = pivot
        floor = max(5, pivot - WINDOW_SIZE)
        while start_idx > floor:
            local_change = abs(_angular_diff(headings[start_idx], headings[start_idx - 5]))
            if local_change < 10:
                break
            start_idx -= 1

        end_idx = pivot
        ceiling = min(len(headings) - 5, pivot + WINDOW_SIZE)
        while end_idx < ceiling:
            local_change = abs(_angular_diff(headings[end_idx + 5], headings[end_idx]))
            if local_change < 5:  # Heading stabilized
                break
            end_idx += 1

        t_start, t_end = times[start_idx], times[end_idx]
        if t_end - t_start > MAX_MANEUVER_DURATION_SEC:
            continue

        cand = _candidate_from_window(
            gps, imu, true_wind, axis_deg, had_wind_axis,
            times, headings, gps_speeds, gps_lats, gps_lons,
            t_start, t_end,
        )
        if cand is None:
            continue
        candidates.append(cand)

    return candidates


def _detection_arrays(gps: list[GpsPoint]):
    """Series shared by every use of the maneuver pipeline (both automatic
    detection and a manual maneuver's on-demand stat computation) — GPS
    course, not IMU heading (mounting offset issues), drives everything.
    ``headings`` is smoothed (plain GPS-course jitter near head-to-wind/
    dead-downwind otherwise triggers spurious candidates); ``raw_headings``
    is kept separately for the wind-axis fallback, which wants the track's
    real shape, not the smoothed one."""
    times = np.array([p.timestamp for p in gps])
    raw_headings = np.array([p.heading_deg for p in gps])
    headings = _smooth_heading(raw_headings)
    gps_speeds = np.array([p.speed_kts for p in gps])
    gps_lats = np.array([p.lat for p in gps])
    gps_lons = np.array([p.lon for p in gps])
    return times, raw_headings, headings, gps_speeds, gps_lats, gps_lons


def resolve_wind_axis(raw_headings: np.ndarray, twd_deg: float | None) -> "tuple[float, bool]":
    """Real wind axis when available, else a synthetic one (the track's
    circular-mean heading) at reduced confidence — same fallback
    ``_detect_candidates`` always used, factored out so the manual-maneuver
    path resolves the axis identically."""
    had_wind_axis = twd_deg is not None
    axis_deg = twd_deg if had_wind_axis else _circular_mean(raw_headings)
    return axis_deg, had_wind_axis


def _candidate_from_window(
    gps: list[GpsPoint],
    imu: list[ImuReading] | None,
    true_wind: list[dict] | None,
    axis_deg: float,
    had_wind_axis: bool,
    times: np.ndarray,
    headings: np.ndarray,
    gps_speeds: np.ndarray,
    gps_lats: np.ndarray,
    gps_lons: np.ndarray,
    t_start: float,
    t_end: float,
) -> "ManeuverCandidate | None":
    """Compute a candidate's type-independent metrics + feature vector for a
    given ``[t_start, t_end]`` window — the "given boundaries, describe this
    maneuver" half of what used to be inlined in ``_detect_candidates``'s
    per-transition loop. Boundary-finding stays the caller's job (either
    ``_detect_candidates``'s rate-of-turn scan, or a user's explicit click
    window — see ``compute_manual_maneuver``), so both paths get identical
    stats/features for the same boundaries. Returns ``None`` if the boat was
    nearly stopped at the start (same gate ``_detect_candidates`` always
    applied) — a maneuver's speed-loss stats are meaningless below that."""
    start_idx = int(np.searchsorted(times, t_start))
    end_idx = min(int(np.searchsorted(times, t_end)), len(times) - 1)

    heading_before = float(headings[start_idx])
    heading_after = float(headings[end_idx])
    heading_change = _angular_diff(heading_after, heading_before)

    # Speed metrics (interpolate GPS speed at maneuver boundaries)
    speed_before = float(np.interp(t_start, times, gps_speeds))
    if speed_before < MIN_BOAT_SPEED_KTS:
        return None

    rel_before = _angular_diff(heading_before, axis_deg)
    rel_after = _angular_diff(heading_after, axis_deg)

    # Find minimum speed during maneuver
    mask = (times >= t_start) & (times <= t_end)
    if mask.sum() > 0:
        speed_min = float(gps_speeds[mask].min())
    else:
        speed_min = float(np.interp((t_start + t_end) / 2, times, gps_speeds))

    # Find speed after and recovery time
    speed_after, recovery_time = _compute_recovery(times, gps_speeds, t_end, speed_before)

    # Heel during maneuver (from IMU)
    max_heel = None
    if imu:
        imu_times_arr = np.array([r.timestamp for r in imu])
        imu_heels = np.array([r.heel_deg for r in imu])
        mask_imu = (imu_times_arr >= t_start) & (imu_times_arr <= t_end)
        if mask_imu.sum() > 0:
            max_heel = float(np.max(np.abs(imu_heels[mask_imu])))

    # Start position
    start_lat = float(np.interp(t_start, times, gps_lats))
    start_lon = float(np.interp(t_start, times, gps_lons))

    ctx = FeatureContext(
        gps=gps,
        imu=imu,
        true_wind=true_wind,
        axis_deg=float(axis_deg),
        had_wind_axis=had_wind_axis,
        t_start=float(t_start),
        t_end=float(t_end),
        heading_before=heading_before,
        heading_after=heading_after,
        speed_before_kts=speed_before,
        speed_min_kts=speed_min,
        speed_after_kts=speed_after,
        recovery_time_sec=recovery_time,
        rel_before=float(rel_before),
        rel_after=float(rel_after),
        max_heel_deg=max_heel,
    )

    return ManeuverCandidate(
        start_time=t_start,
        end_time=t_end,
        duration_sec=t_end - t_start,
        heading_change_deg=heading_change,
        speed_before_kts=speed_before,
        speed_min_kts=speed_min,
        speed_after_kts=speed_after,
        recovery_time_sec=recovery_time,
        start_lat=start_lat,
        start_lon=start_lon,
        features=extract_features(ctx),
    )


def compute_manual_maneuver(
    gps: list[GpsPoint],
    imu: list[ImuReading] | None,
    twd_deg: float | None,
    true_wind: list[dict] | None,
    t_start: float,
    t_end: float,
    maneuver_type: ManeuverType,
) -> Maneuver:
    """Stats/features for a user-specified maneuver window — the manual-add
    counterpart to ``_detect_candidates``/``_finalize``, reusing the exact
    same math via ``_candidate_from_window`` instead of duplicating it (see
    ``routers/sessions.py::add_maneuver`` for the caller, via a worker
    round-trip). Skips ``_detect_candidates``'s transition-scan entirely
    (the user already gives exact boundaries) and bypasses ``_finalize``'s
    per-type minimum-heading-change gate — a user explicitly placing a
    maneuver overrides that heuristic; it exists to filter out the
    algorithm's own noise, not a human's judgment.

    Raises ``ValueError`` if the window isn't a valid maneuver window (boat
    nearly stopped at the start) — the caller should surface this as an
    error, not silently drop the request the way automatic detection does.
    """
    times, _raw_headings, headings, gps_speeds, gps_lats, gps_lons = _detection_arrays(gps)
    axis_deg, had_wind_axis = resolve_wind_axis(_raw_headings, twd_deg)
    cand = _candidate_from_window(
        gps, imu, true_wind, axis_deg, had_wind_axis,
        times, headings, gps_speeds, gps_lats, gps_lons,
        t_start, t_end,
    )
    if cand is None:
        raise ValueError(
            f"Cannot compute a maneuver for [{t_start}, {t_end}]: "
            f"boat speed at t_start is below {MIN_BOAT_SPEED_KTS}kts."
        )
    maneuver = _finalize(cand, maneuver_type, enforce_min_heading_change=False)
    assert maneuver is not None  # enforce_min_heading_change=False never returns None
    return maneuver


def _finalize(
    cand: ManeuverCandidate,
    maneuver_type: ManeuverType,
    enforce_min_heading_change: bool = True,
) -> Maneuver | None:
    """Apply the per-type minimum-heading-change gate and build the final
    ``Maneuver``. Returns ``None`` (the old ``continue``) when the heading
    change is below the type's floor. Rounding matches the previous inline
    construction exactly; ``cand.features`` (which includes ``max_heel_deg`` —
    see ``maneuver_features._max_heel_deg``) is carried onto the maneuver for
    persistence.

    ``enforce_min_heading_change=False`` (used only by
    ``compute_manual_maneuver``) skips the gate entirely — a user placing a
    maneuver by hand overrides the heuristic that exists to filter the
    algorithm's own false positives, not a human's judgment."""
    min_change = (MIN_GYBE_HEADING_CHANGE_DEG
                  if maneuver_type in (ManeuverType.GYBE, ManeuverType.COURSE_CHANGE)
                  else MIN_TACK_HEADING_CHANGE_DEG)
    if enforce_min_heading_change and abs(cand.heading_change_deg) < min_change:
        return None

    return Maneuver(
        maneuver_type=maneuver_type,
        start_time=cand.start_time,
        end_time=cand.end_time,
        duration_sec=round(cand.duration_sec, 1),
        speed_loss_kts=round(cand.speed_before_kts - cand.speed_min_kts, 2),
        speed_before_kts=round(cand.speed_before_kts, 2),
        speed_min_kts=round(cand.speed_min_kts, 2),
        speed_after_kts=round(cand.speed_after_kts, 2),
        recovery_time_sec=round(cand.recovery_time_sec, 1),
        heading_change_deg=round(cand.heading_change_deg, 1),
        start_lat=cand.start_lat,
        start_lon=cand.start_lon,
        features=cand.features,
    )


def _smooth_heading(headings_deg: np.ndarray, window: int = HEADING_SMOOTH_WINDOW) -> np.ndarray:
    """Centered circular moving average (via unit vectors, to avoid
    wraparound artifacts a plain arithmetic mean would introduce) — reduces
    compass/GPS-course jitter that would otherwise trigger spurious
    rate-of-turn candidates in the sliding-window scan."""
    if len(headings_deg) < window:
        return headings_deg
    rad = np.radians(headings_deg)
    kernel = np.ones(window) / window
    pad_before, pad_after = window // 2, window - 1 - window // 2
    cos_s = np.convolve(np.pad(np.cos(rad), (pad_before, pad_after), mode="edge"), kernel, mode="valid")
    sin_s = np.convolve(np.pad(np.sin(rad), (pad_before, pad_after), mode="edge"), kernel, mode="valid")
    return np.degrees(np.arctan2(sin_s, cos_s)) % 360


def _tack_side(heading_deg: float, axis_deg: float) -> int:
    """+1 = starboard tack (wind from the right of the axis), -1 = port."""
    return 1 if _angular_diff(heading_deg, axis_deg) > 0 else -1


def _debounced_sides(sides: np.ndarray, times: np.ndarray, min_run_sec: float) -> np.ndarray:
    """Minimum-dwell-time filter on a per-sample tack-side sequence: any run
    shorter than `min_run_sec` is absorbed into the run before it. This is
    what actually distinguishes a genuine maneuver from a brief wiggle or an
    aborted attempt that rounds back — a transition only survives if *both*
    neighboring sides were themselves genuinely settled, not just the side
    after it (checking one side only would let an aborted maneuver's rebound
    read as a fresh, valid transition). Iterates to convergence since
    absorbing one short run can join two longer runs that then need
    re-checking (rare in practice, bounded for safety)."""
    sides = sides.copy()
    n = len(sides)
    for _ in range(5):
        changed = False
        i = 0
        while i < n:
            j = i
            while j < n and sides[j] == sides[i]:
                j += 1
            run_sec = times[min(j, n - 1)] - times[i]
            if run_sec < min_run_sec and 0 < i < n:
                sides[i:j] = sides[i - 1]
                changed = True
            i = j
        if not changed:
            break
    return sides


def _compute_recovery(
    gps_times: np.ndarray,
    gps_speeds: np.ndarray,
    maneuver_end: float,
    speed_before: float,
) -> tuple[float, float]:
    """Find speed after maneuver and time to recover to 90% entry speed."""
    target = speed_before * SPEED_RECOVERY_THRESHOLD
    mask = gps_times > maneuver_end
    future_times = gps_times[mask]
    future_speeds = gps_speeds[mask]

    if len(future_times) == 0:
        return speed_before, 0.0

    # Speed 5 seconds after maneuver
    t_after = maneuver_end + 5.0
    speed_after = float(np.interp(t_after, gps_times, gps_speeds))

    # Recovery time
    window_mask = (future_times - maneuver_end) < MAX_RECOVERY_WINDOW_SEC
    window_speeds = future_speeds[window_mask]
    window_times = future_times[window_mask]

    recovered = window_speeds >= target
    if recovered.any():
        first_idx = np.argmax(recovered)
        recovery_time = window_times[first_idx] - maneuver_end
    else:
        recovery_time = MAX_RECOVERY_WINDOW_SEC

    return speed_after, recovery_time


def maneuver_summary(maneuvers: list[Maneuver]) -> dict:
    """Compute summary statistics for all maneuvers.

    ``course_changes`` is emitted for completeness (the third class); with the
    active geometric classifier no maneuver is labelled ``course_change``, so
    it stays at ``{"count": 0}`` today.
    """
    tacks = [m for m in maneuvers if m.maneuver_type == ManeuverType.TACK]
    gybes = [m for m in maneuvers if m.maneuver_type == ManeuverType.GYBE]
    course_changes = [m for m in maneuvers if m.maneuver_type == ManeuverType.COURSE_CHANGE]

    def _stats(group: list[Maneuver]) -> dict:
        if not group:
            return {"count": 0}
        speeds_lost = [m.speed_loss_kts for m in group]
        recovery_times = [m.recovery_time_sec for m in group]
        durations = [m.duration_sec for m in group]
        return {
            "count": len(group),
            "avg_speed_loss_kts": round(np.mean(speeds_lost), 2),
            "avg_recovery_sec": round(np.mean(recovery_times), 1),
            "avg_duration_sec": round(np.mean(durations), 1),
            "best_speed_loss_kts": round(min(speeds_lost), 2),
            "worst_speed_loss_kts": round(max(speeds_lost), 2),
        }

    return {
        "tacks": _stats(tacks),
        "gybes": _stats(gybes),
        "course_changes": _stats(course_changes),
        "total": len(maneuvers),
    }
