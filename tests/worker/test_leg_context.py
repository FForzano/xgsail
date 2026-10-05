"""`in_beat`: a reach tacked on at both ends was sailed as part of a beat."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workers" / "process_upload"))

from processing.models import GpsPoint, Maneuver, ManeuverType
from processing.straight_lines import segment_legs

T0 = 1_800_000_000.0
LEG_S = 60
TURN_S = 5
TACK, GYBE = ManeuverType.TACK, ManeuverType.GYBE


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
