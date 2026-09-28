"""Tack/gybe wind observations and their local blend into a modelled wind.

Regression: a modelled wind direction ~30° off put every upwind leg of a beat
on the same tack — the other tack's legs read as reaches (TWA ≈ 78° against
the 70° threshold). The boat's own tacks bisect the true wind, and blending
them in locally puts both tacks back upwind.

Numbers behind the ``gps_tack`` prior (2.0), its 2 km distance decay and
15 min time decay, for a row fused from four Open-Meteo models (weight
0.6+0.6+0.35+0.35 = 1.9) that all share a 30° bias:

- 5 clean tacks in 15 min (confidence ~0.94, ~0.3 km and ≤7 min away) weigh
  ~2.0 x 0.94 x 0.85 x 0.63 ≈ 1.0 each; the direction residual stays under
  ~11° across the whole track (8 tacks: under ~7°) — both tacks upwind again;
- one sloppy tack (12° heading std, nothing to cross-check it against:
  confidence ~0.2) weighs ~0.4 and moves the row by ~5°;
- at 10 km the same clean tack is worth exp(-10/2) ≈ 0.7% of itself, and
  30 min away exp(-2) ≈ 14%."""

import json
import math
import random

import pytest

from analyzer import _avg_twd, analyze_session
from processing.models import GpsPoint, Maneuver, ManeuverType
from processing.straight_lines import segment_legs
from processing.tack_wind import (
    blend_observations,
    observations_from_bundle,
    observations_from_maneuvers,
    seed_observations,
    to_payload,
)
from processing.wind_estimation import weighted_fusion

T0 = 1_800_000_000.0
HALF = 48.0  # 96° tacking angle over ground — a realistic dinghy beat
MODELS = ("icon_d2", "icon_eu", "gfs_seamless", "ecmwf_ifs025")


def _diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _sail(axis, halves, *, leg_s=90, turn_s=6, noise=3.0, speed=4.5, seed=1,
          lat=44.8, lon=12.3, kind=ManeuverType.TACK):
    """A 1 Hz track alternating ``axis ± halves[leg]`` with a ``turn_s`` turn
    between legs; returns ``(gps, maneuvers)`` with each turn as a maneuver."""
    rnd = random.Random(seed)
    gps, maneuvers, t, prev = [], [], T0, None
    for leg, half in enumerate(halves):
        target = (axis + (half if leg % 2 == 0 else -half)) % 360.0
        if prev is not None:
            start = t
            delta = (target - prev + 180.0) % 360.0 - 180.0
            for k in range(turn_s):
                gps.append(GpsPoint(t, lat, lon, speed * 0.7, (prev + delta * (k + 1) / turn_s) % 360.0))
                t += 1
            maneuvers.append(Maneuver(kind, start, t - 1, turn_s, 1.5, speed, speed * 0.7,
                                      speed, 5.0, delta))
        for _ in range(leg_s):
            h = (target + rnd.gauss(0, noise)) % 360.0
            gps.append(GpsPoint(t, lat, lon, speed, h))
            step = speed * 1852 / 3600
            lat += step * math.cos(math.radians(h)) / 111_320
            lon += step * math.sin(math.radians(h)) / (111_320 * math.cos(math.radians(lat)))
            t += 1
        prev = target
    return gps, maneuvers


def _bundle(twd, **extra):
    rows = [{"observed_at": 0, "twd_deg": twd % 360, "tws_kts": 10},
            {"observed_at": 2e9, "twd_deg": twd % 360, "tws_kts": 10}]
    return [{"lat": 44.8, "lng": 12.3, "real_stations": [], "grid_estimates": [],
             "model_candidates": {m: rows for m in MODELS}, **extra}]


def _obs(twd, *, t=T0, lat=44.8, lng=12.3, confidence=0.95):
    return {"observed_at": t, "lat": lat, "lng": lng, "twd_deg": twd,
            "confidence": confidence, "kind": "tack"}


# --- observations --------------------------------------------------------------

@pytest.mark.parametrize("true_twd", [0.0, 5.0, 355.0, 180.0])
def test_tack_bisector_recovers_the_wind_across_the_wrap(true_twd):
    gps, maneuvers = _sail(true_twd, [HALF] * 4)
    obs = observations_from_maneuvers(gps, maneuvers)
    assert len(obs) == 3
    for o in obs:
        assert _diff(o["twd_deg"], true_twd) < 1.5
        assert 0.0 <= o["twd_deg"] < 360.0
        assert o["kind"] == "tack"
        assert 0.0 < o["confidence"] <= 1.0


def test_observation_sits_at_the_maneuver():
    gps, maneuvers = _sail(0.0, [HALF] * 2)
    [o] = observations_from_maneuvers(gps, maneuvers)
    m = maneuvers[0]
    assert m.start_time <= o["observed_at"] <= m.end_time
    at = min(gps, key=lambda p: abs(p.timestamp - o["observed_at"]))
    assert o["lat"] == pytest.approx(at.lat, abs=1e-4)
    assert o["lng"] == pytest.approx(at.lon, abs=1e-4)


def test_precise_tacks_are_trusted_more_than_sloppy_ones():
    precise = observations_from_maneuvers(*_sail(0.0, [HALF] * 5, noise=2.0))
    sloppy = observations_from_maneuvers(*_sail(0.0, [HALF] * 5, noise=12.0))
    assert min(o["confidence"] for o in precise) > 0.85
    assert max(o["confidence"] for o in sloppy) < 0.5 * min(o["confidence"] for o in precise)


def test_asymmetric_tack_is_an_outlier_against_the_session_median():
    # Legs 3/4 are a close-hauled leg then a 75° reach: tacking angle 123°
    # instead of ~96°, and its bisector is off by ~14°.
    gps, maneuvers = _sail(0.0, [HALF, HALF, HALF, HALF, 75.0, HALF, HALF])
    obs = observations_from_maneuvers(gps, maneuvers)
    assert len(obs) == 6
    worst = min(obs, key=lambda o: o["confidence"])
    assert _diff(worst["twd_deg"], 0.0) > 10
    others = [o["confidence"] for o in obs if o is not worst and _diff(o["twd_deg"], 0.0) < 2]
    assert worst["confidence"] < 0.1 * min(others)


def test_a_lone_tack_cannot_be_cross_checked():
    lone = observations_from_maneuvers(*_sail(0.0, [HALF] * 2))
    many = observations_from_maneuvers(*_sail(0.0, [HALF] * 5))
    assert lone[0]["confidence"] < 0.6 * min(o["confidence"] for o in many)


def test_gybe_bisector_points_downwind_and_is_trusted_less():
    # Broad reaches at TWA 150° either side of TWD 10° → heading 190 ± 30.
    gybes = observations_from_maneuvers(*_sail(190.0, [30.0] * 5, kind=ManeuverType.GYBE))
    tacks = observations_from_maneuvers(*_sail(10.0, [HALF] * 5))
    assert len(gybes) == 4
    assert all(_diff(o["twd_deg"], 10.0) < 1.5 and o["kind"] == "gybe" for o in gybes)
    assert max(o["confidence"] for o in gybes) < min(o["confidence"] for o in tacks)


@pytest.mark.parametrize("kwargs", [
    {"halves": [85.0] * 3},                  # 170° "tack": reach to reach
    {"halves": [HALF] * 3, "speed": 1.0},     # drifting — COG is noise
    {"halves": [HALF] * 3, "leg_s": 12},      # no steady course either side
])
def test_implausible_maneuvers_are_rejected(kwargs):
    halves = kwargs.pop("halves")
    assert observations_from_maneuvers(*_sail(0.0, halves, **kwargs)) == []


def test_course_changes_yield_no_observation():
    gps, maneuvers = _sail(0.0, [HALF] * 3, kind=ManeuverType.COURSE_CHANGE)
    assert observations_from_maneuvers(gps, maneuvers) == []


def test_payload_shape():
    gps, maneuvers = _sail(0.0, [HALF] * 2)
    [p] = to_payload(observations_from_maneuvers(gps, maneuvers))
    assert set(p) == {"observed_at", "lat", "lng", "twd_deg", "confidence", "kind"}
    assert p["observed_at"].endswith("+00:00")


# --- bundle observations ---------------------------------------------------------

def test_bundle_observations_are_parsed_and_deduped_by_id():
    shared = {"id": "a", "observed_at": "2027-01-15T08:00:00+00:00", "lat": 44.8,
              "lng": 12.3, "twd_deg": 361.0, "confidence": 0.9, "kind": "tack"}
    other = {**shared, "id": "b", "twd_deg": 10.0}
    bundle = [{"track_observations": [shared, other]},
              {"track_observations": [shared]},
              {"lat": 1, "lng": 1}]  # an older cache: no key at all
    obs = observations_from_bundle(bundle)
    assert [o["twd_deg"] for o in obs] == [1.0, 10.0]
    assert isinstance(obs[0]["observed_at"], float)
    assert observations_from_bundle([{"lat": 1}]) == []


def test_other_boats_observations_correct_a_session_with_no_tacks():
    # This boat only reaches (no tacks of its own); a neighbour tacked nearby.
    gps, _ = _sail(90.0, [0.0], leg_s=600)
    neighbour = [{"id": str(i), "observed_at": gps[i].timestamp, "lat": gps[i].lat,
                  "lng": gps[i].lon, "twd_deg": 0.0, "confidence": 0.95, "kind": "tack"}
                 for i in range(60, 600, 150)]
    bundle = _bundle(30.0, track_observations=neighbour)
    true_wind = weighted_fusion(gps, [], None, bundle)
    blend_observations(gps, true_wind, observations_from_bundle(bundle * 3))
    assert all(_diff(r["twd_deg"], 0.0) < 12 for r in true_wind)

    # The same four repeated across waypoints count once.
    once = weighted_fusion(gps, [], None, bundle)
    blend_observations(gps, once, observations_from_bundle(bundle))
    assert [r["twd_deg"] for r in once] == [r["twd_deg"] for r in true_wind]


# --- blend ---------------------------------------------------------------------

def _row(twd=30.0, source="fusion", confidence=1.9):
    return {"timestamp": T0, "twd_deg": twd, "tws_kts": 10.0, "heading_deg": 0.0,
            "twa_deg": twd, "source": source, "confidence": confidence}


def _blend_one(obs, row=None):
    row = row or _row()
    blend_observations([GpsPoint(T0, 44.8, 12.3, 4.5, 0.0)], [row], obs)
    return row


def test_effect_decays_with_distance_and_is_local():
    km = 1 / 111.32  # degrees of latitude per km
    moved = [30.0 - _blend_one([_obs(0.0, lat=44.8 + d * km)])["twd_deg"] for d in (0, 1, 3, 10)]
    assert moved[0] > moved[1] > moved[2] > moved[3] >= 0
    assert moved[3] < 0.5


def test_effect_decays_with_time():
    moved = [30.0 - _blend_one([_obs(0.0, t=T0 - dt)])["twd_deg"] for dt in (0, 900, 3600, 4 * 3600)]
    assert moved[0] > moved[1] > moved[2] > moved[3] >= 0
    assert moved[3] < 1.0


def test_one_sloppy_tack_barely_moves_a_four_model_row():
    gps, maneuvers = _sail(0.0, [HALF] * 2, noise=12.0)
    true_wind = weighted_fusion(gps, [], None, _bundle(30.0))
    assert true_wind[0]["confidence"] == pytest.approx(1.9)
    blend_observations(gps, true_wind, observations_from_maneuvers(gps, maneuvers))
    assert all(_diff(r["twd_deg"], 30.0) < 5 for r in true_wind)


def test_blend_recomputes_twa_and_leaves_speed():
    row = _blend_one([_obs(0.0)] * 5)
    assert row["tws_kts"] == 10.0
    assert row["twa_deg"] == pytest.approx(row["twd_deg"])  # heading 0
    assert row["twd_deg"] < 10


def test_sensor_rows_are_never_touched():
    row = _blend_one([_obs(0.0)] * 5, _row(source="sensor"))
    assert row["twd_deg"] == 30.0 and row["twa_deg"] == 30.0


def test_blend_wraps_around_north():
    row = _blend_one([_obs(350.0)] * 20, _row(twd=10.0))
    assert _diff(row["twd_deg"], 350.0) < 3


# --- regression: biased model, realistic beat ----------------------------------

@pytest.mark.parametrize("bias", [-30.0, 30.0])
def test_biased_model_still_yields_upwind_legs_on_both_tacks(bias):
    gps, maneuvers = _sail(0.0, [HALF] * 8)
    true_wind = weighted_fusion(gps, [], None, _bundle(bias))
    before = segment_legs(gps, maneuvers, true_wind)
    assert {l.leg_type.value for l in before} == {"upwind", "reach"}  # the bug

    blend_observations(gps, true_wind, observations_from_maneuvers(gps, maneuvers))
    legs = segment_legs(gps, maneuvers, true_wind)
    assert len(legs) == 8
    assert all(l.leg_type.value == "upwind" for l in legs)
    assert {l.tack for l in legs} == {"port", "starboard"}
    assert all(r["tws_kts"] == pytest.approx(10.0) for r in true_wind)


def test_a_few_tacks_in_fifteen_minutes_overcome_the_bias():
    gps, maneuvers = _sail(0.0, [HALF] * 5, leg_s=175)
    assert gps[-1].timestamp - gps[0].timestamp < 15 * 60
    true_wind = weighted_fusion(gps, [], None, _bundle(30.0))
    blend_observations(gps, true_wind, observations_from_maneuvers(gps, maneuvers))
    assert all(_diff(r["twd_deg"], 0.0) < 12 for r in true_wind)


def test_unbiased_model_is_not_made_worse():
    gps, maneuvers = _sail(0.0, [HALF] * 8)
    true_wind = weighted_fusion(gps, [], None, _bundle(0.0))
    blend_observations(gps, true_wind, observations_from_maneuvers(gps, maneuvers))
    assert all(_diff(r["twd_deg"], 0.0) < 1.0 for r in true_wind)


def test_analyze_session_end_to_end(tmp_path):
    """Real maneuver detection (on the Kalman-smoothed track) against a 30°
    biased model: both tacks upwind, observations emitted in wire shape."""
    gps, _ = _sail(0.0, [HALF] * 8)
    (tmp_path / "gps.json").write_text(json.dumps([
        {"timestamp": p.timestamp, "lat": p.lat, "lon": p.lon,
         "speed_kts": p.speed_kts, "heading_deg": p.heading_deg} for p in gps]))
    (tmp_path / "wind_cache.json").write_text(json.dumps(_bundle(30.0)))

    result = analyze_session(tmp_path)

    assert {l["leg_type"] for l in result["legs"]} == {"upwind"}
    assert {l["tack"] for l in result["legs"]} == {"port", "starboard"}
    observations = result["track_wind_observations"]
    assert len(observations) == 7
    assert all(isinstance(o["observed_at"], str) for o in observations)


def test_analysis_without_maneuvers_emits_an_empty_list(tmp_path):
    (tmp_path / "gps.json").write_text(json.dumps([
        {"timestamp": T0 + i, "lat": 45.0 + 1e-5 * i, "lon": 9.0, "speed_kts": 5.0,
         "heading_deg": 0.0} for i in range(60)]))
    (tmp_path / "wind_cache.json").write_text(json.dumps(_bundle(30.0)))
    assert analyze_session(tmp_path)["track_wind_observations"] == []


def test_average_wind_direction_is_circular():
    assert _diff(_avg_twd([{"twd_deg": 350.0}, {"twd_deg": 10.0}]), 0.0) < 1e-6
    assert _avg_twd([]) is None


# --- re-classification to a fixed point -------------------------------------

def _write_session(tmp_path, gps, bundle):
    (tmp_path / "gps.json").write_text(json.dumps([
        {"timestamp": p.timestamp, "lat": p.lat, "lon": p.lon,
         "speed_kts": p.speed_kts, "heading_deg": p.heading_deg} for p in gps]))
    (tmp_path / "wind_cache.json").write_text(json.dumps(bundle))


def test_model_too_far_off_to_see_any_tack_is_recovered(tmp_path):
    """Regression: at 50° of model bias every tack of a 96° beat reads as a
    same-tack course change, so a single pass had no tack to correct from and
    every leg stayed misclassified. Seeds move the axis, the next pass sees
    real tacks."""
    gps, _ = _sail(0.0, [HALF] * 8)
    _write_session(tmp_path, gps, _bundle(50.0))

    result = analyze_session(tmp_path)

    assert {l["leg_type"] for l in result["legs"]} == {"upwind"}
    assert {l["tack"] for l in result["legs"]} == {"port", "starboard"}
    assert result["track_wind_observations"]
    assert all(o["kind"] == "tack" for o in result["track_wind_observations"])


def test_seeds_need_agreeing_bisectors():
    beat_gps, beat = _sail(0.0, [HALF] * 6, kind=ManeuverType.COURSE_CHANGE)
    seeds = seed_observations(beat_gps, beat, model_twd_deg=50.0)
    assert len(seeds) == 5 and all(_diff(o["twd_deg"], 0.0) < 3 for o in seeds)

    # Same count of tacking-angle turns, but bisectors scattered (a course
    # around marks): nothing to agree on, no seed.
    wander_gps, wander = [], []
    for i, axis in enumerate((0.0, 70.0, 140.0, 210.0)):
        g, m = _sail(axis, [HALF] * 2, kind=ManeuverType.COURSE_CHANGE, seed=i,
                     lat=44.8 + i * 0.01)
        offset = i * 1000.0
        wander_gps += [GpsPoint(p.timestamp + offset, p.lat, p.lon, p.speed_kts, p.heading_deg)
                       for p in g]
        wander += [Maneuver(x.maneuver_type, x.start_time + offset, x.end_time + offset,
                            x.duration_sec, x.speed_loss_kts, x.speed_before_kts,
                            x.speed_min_kts, x.speed_after_kts, x.recovery_time_sec,
                            x.heading_change_deg) for x in m]
    assert seed_observations(wander_gps, wander, model_twd_deg=0.0) == []


def test_refinement_leaves_an_unbiased_session_alone(tmp_path):
    gps, _ = _sail(0.0, [HALF] * 8)
    _write_session(tmp_path, gps, _bundle(0.0))
    result = analyze_session(tmp_path)
    assert all(_diff(r["twd_deg"], 0.0) < 1.0 for r in result["true_wind"])
