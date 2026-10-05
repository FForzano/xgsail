"""Leg segmentation and context: unsteady spans split into steady legs, and
`in_beat`/`in_run` reaches decided by the nearest tack/gybe on each side."""

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workers" / "process_upload"))

from processing.models import GpsPoint, Maneuver, ManeuverType
from processing.straight_lines import MAX_HEADING_STD_DEG, _circular_std, segment_legs

T0 = 1_800_000_000.0
LEG_S = 60
TURN_S = 5
TACK, GYBE, COURSE = ManeuverType.TACK, ManeuverType.GYBE, ManeuverType.COURSE_CHANGE


def _legs(twas, kinds):
    """One steady leg per TWA, a maneuver of the given kind between each pair."""
    gps, maneuvers, wind, t = [], [], [], T0
    for n, twa in enumerate(twas):
        for _ in range(LEG_S):
            gps.append(GpsPoint(t, 44.8, 12.3, 5.0, 90.0))
            wind.append({"timestamp": t, "twa_deg": twa, "tws_kts": 10.0})
            t += 1
        if n < len(kinds):
            maneuvers.append(Maneuver(kinds[n], t, t + TURN_S, TURN_S, 1.0, 5.0, 3.0, 5.0, 5.0, 90.0))
            t += TURN_S + 1
    return segment_legs(gps, maneuvers, wind)


def test_reach_between_two_tacks_is_in_beat():
    legs = _legs([50, 80, 50], [TACK, TACK])
    assert [l.leg_type.value for l in legs] == ["upwind", "reach", "upwind"]
    assert [l.in_beat for l in legs] == [False, True, False]


def test_reach_between_tack_and_gybe_is_not_in_beat():
    assert not _legs([50, 80, 150], [TACK, GYBE])[1].in_beat


def test_reach_beyond_95_degrees_is_not_in_beat():
    assert not _legs([50, 100, 50], [TACK, TACK])[1].in_beat


def test_session_edge_legs_are_not_in_beat():
    legs = _legs([80, 80], [TACK])
    assert [l.leg_type.value for l in legs] == ["reach", "reach"]
    assert [l.in_beat for l in legs] == [False, False]


def test_reach_between_two_gybes_is_in_run():
    legs = _legs([150, 100, 150], [GYBE, GYBE])
    assert [l.leg_type.value for l in legs] == ["downwind", "reach", "downwind"]
    assert [l.in_run for l in legs] == [False, True, False]
    assert not legs[1].in_beat


def test_reach_between_two_tacks_is_not_in_run():
    legs = _legs([50, 90, 50], [TACK, TACK])
    assert not legs[1].in_run and legs[1].in_beat


def test_reach_below_85_degrees_is_not_in_run():
    assert not _legs([150, 80, 150], [GYBE, GYBE])[1].in_run


def test_context_skips_course_changes():
    legs = _legs([50, 80, 80, 50], [TACK, COURSE, TACK])
    assert [l.in_beat for l in legs] == [False, True, True, False]
    legs = _legs([150, 100, 100, 150], [GYBE, COURSE, GYBE])
    assert [l.in_run for l in legs] == [False, True, True, False]


def test_mixed_crossings_or_session_edge_give_neither_flag():
    for twas, kinds in (([150, 90, 50], [GYBE, TACK]), ([90, 150], [GYBE])):
        legs = _legs(twas, kinds)
        assert not any(l.in_beat or l.in_run for l in legs)


# --- regression: unsteady downwind spans were dropped whole -------------------

def _wavy_span(rnd, headings, twa_offset, t0=T0):
    """1 Hz sailing along ``headings``: GPS noise plus wave yaw."""
    gps, wind = [], []
    for k, h in enumerate(headings):
        t = t0 + k
        yaw = 8.0 * math.sin(2 * math.pi * k / 12) + rnd.gauss(0, 6.0)
        gps.append(GpsPoint(t, 44.8, 12.3, 6.0, (h + yaw) % 360))
        wind.append({"timestamp": t, "twa_deg": h - twa_offset, "tws_kts": 12.0})
    return gps, wind


def test_gradual_bear_away_splits_into_two_downwind_legs():
    # 125° TWA, then bearing away 50° at 1°/s — below the maneuver detector's
    # 2°/s gate, so no maneuver — then 175°. Heading crosses north (wrap).
    headings = [340.0] * 120 + [340.0 + k for k in range(1, 51)] + [390.0] * 120
    gps, wind = _wavy_span(random.Random(7), headings, 340.0 - 125.0)
    whole_std = _circular_std([p.heading_deg for p in gps])
    assert whole_std > MAX_HEADING_STD_DEG  # the bug: one span, dropped

    legs = segment_legs(gps, [], wind)
    assert [l.leg_type.value for l in legs] == ["downwind", "downwind"]
    assert legs[0].avg_twa_deg < 135 < 165 < legs[1].avg_twa_deg
    assert sum(l.duration_sec for l in legs) > 240


def test_split_boundary_does_not_break_context():
    # Gybe, a reach luffing up gradually from 118° to 88° TWA, gybe.
    rnd = random.Random(3)
    reach = [0.0] * 120 + [-float(k) for k in range(1, 31)] + [-30.0] * 120
    spans = [([0.0] * 60, -150.0), (reach, -118.0), ([0.0] * 60, -150.0)]
    gps, wind, maneuvers, t = [], [], [], T0
    for n, (headings, offset) in enumerate(spans):
        if n:
            maneuvers.append(Maneuver(GYBE, t, t + TURN_S, TURN_S, 1.0, 6.0, 4.0, 6.0, 5.0, 90.0))
            t += TURN_S + 1
        span_gps, span_wind = _wavy_span(rnd, headings, offset, t)
        gps += span_gps
        wind += span_wind
        t += len(headings)

    legs = segment_legs(gps, maneuvers, wind)
    assert [l.leg_type.value for l in legs] == ["downwind", "reach", "reach", "downwind"]
    assert [l.in_run for l in legs] == [False, True, True, False]


def test_long_wavy_steady_leg_is_not_fragmented():
    gps, wind = _wavy_span(random.Random(11), [200.0] * 900, 200.0 - 150.0)
    legs = segment_legs(gps, [], wind)
    assert len(legs) == 1
    assert legs[0].num_points == 900
