"""Two-stage maneuver detection: behavior-preservation golden, the classifier
registry, the configurable feature schema, the false-alarm/reject path, and
the (dormant) course_change third class.

The golden test is the safety net for the Stage1/Stage2 refactor: the set of
detected maneuvers and every previously-existing field must stay byte-for-byte
identical (only the additive ``features`` field is new)."""

import math
from dataclasses import asdict

import pytest

from processing.maneuvers import _detect_candidates, _finalize, detect_maneuvers
from processing.maneuver_classification import (
    ACTIVE_CLASSIFIER,
    CLASSIFIERS,
    _load_maneuver_model,
    _ml_classifier,
    classify_maneuver,
    geometric_classifier,
)
from processing.maneuver_features import (
    CORE_FEATURES,
    ENABLED_FEATURES,
    FEATURE_EXTRACTORS,
    FeatureContext,
    extract_features,
)
from processing.models import GpsPoint, ImuReading, ManeuverCandidate, ManeuverType


# --------------------------------------------------------------------------- #
# Fixtures: a deterministic upwind zig-zag (3 tacks) + a downwind gybe pair.
# --------------------------------------------------------------------------- #

def _leg(points, t0, lat0, lon0, heading, speed, n):
    for i in range(n):
        lat = lat0 + 0.00005 * i * math.cos(math.radians(heading))
        lon = lon0 + 0.00005 * i * math.sin(math.radians(heading))
        points.append(GpsPoint(timestamp=float(t0 + i), lat=lat, lon=lon,
                               speed_kts=speed, heading_deg=heading % 360))
    return t0 + n, lat0, lon0


def build_track():
    gps = []
    t, lat, lon = 0.0, 45.0, 9.0
    for h in (45, -45, 45, -45):
        t, lat, lon = _leg(gps, t, lat, lon, h, 6.0, 40)
    t, lat, lon = _leg(gps, t, lat, lon, 150, 6.5, 40)
    t, lat, lon = _leg(gps, t, lat, lon, 210, 6.5, 40)
    return gps


def build_imu(gps):
    return [ImuReading(timestamp=p.timestamp, heading_deg=p.heading_deg,
                       pitch_deg=0.0, heel_deg=12.0) for p in gps]


# Frozen output of the PRE-refactor detect_maneuvers (excluding `features`).
GOLDEN = [
    {"maneuver_type": "tack", "start_time": 37.0, "end_time": 42.0, "duration_sec": 5.0,
     "speed_loss_kts": 0.0, "speed_before_kts": 6.0, "speed_min_kts": 6.0,
     "speed_after_kts": 6.0, "recovery_time_sec": 1.0, "heading_change_deg": -90.0,
     "distance_lost_m": None,
     "start_lat": 45.001308147545195, "start_lon": 9.001308147545195},
    {"maneuver_type": "tack", "start_time": 77.0, "end_time": 82.0, "duration_sec": 5.0,
     "speed_loss_kts": 0.0, "speed_before_kts": 6.0, "speed_min_kts": 6.0,
     "speed_after_kts": 6.0, "recovery_time_sec": 1.0, "heading_change_deg": 90.0,
     "distance_lost_m": None,
     "start_lat": 45.001308147545195, "start_lon": 8.998691852454805},
    {"maneuver_type": "tack", "start_time": 117.0, "end_time": 122.0, "duration_sec": 5.0,
     "speed_loss_kts": 0.0, "speed_before_kts": 6.0, "speed_min_kts": 6.0,
     "speed_after_kts": 6.0, "recovery_time_sec": 1.0, "heading_change_deg": -90.0,
     "distance_lost_m": None,
     "start_lat": 45.001308147545195, "start_lon": 9.001308147545195},
    {"maneuver_type": "gybe", "start_time": 158.0, "end_time": 161.0, "duration_sec": 3.0,
     "speed_loss_kts": 0.0, "speed_before_kts": 6.0, "speed_min_kts": 6.0,
     "speed_after_kts": 6.5, "recovery_time_sec": 1.0, "heading_change_deg": -155.2,
     "distance_lost_m": None,
     "start_lat": 45.001343502884254, "start_lon": 8.998656497115746},
    {"maneuver_type": "gybe", "start_time": 197.0, "end_time": 202.0, "duration_sec": 5.0,
     "speed_loss_kts": 0.0, "speed_before_kts": 6.5, "speed_min_kts": 6.5,
     "speed_after_kts": 6.5, "recovery_time_sec": 1.0, "heading_change_deg": 60.0,
     "distance_lost_m": None,
     "start_lat": 44.998397853003, "start_lon": 9.000925},
]


def _core(maneuvers):
    out = []
    for m in maneuvers:
        d = asdict(m)
        d["maneuver_type"] = d["maneuver_type"].value
        d.pop("features", None)
        out.append(d)
    return out


# --------------------------------------------------------------------------- #
# Behavior preservation
# --------------------------------------------------------------------------- #

def test_golden_identity():
    gps = build_track()
    maneuvers = detect_maneuvers(gps, build_imu(gps), 0.0)
    assert _core(maneuvers) == GOLDEN


def test_true_wind_does_not_change_detection():
    """Passing the true_wind series only feeds features — the detected set and
    its existing fields must be unchanged."""
    gps = build_track()
    tw = [{"timestamp": p.timestamp, "twd_deg": 0.0, "tws_kts": 12.0} for p in gps]
    with_wind = detect_maneuvers(gps, build_imu(gps), 0.0, tw)
    assert _core(with_wind) == GOLDEN


def test_maneuvers_carry_features():
    gps = build_track()
    maneuvers = detect_maneuvers(gps, build_imu(gps), 0.0)
    assert maneuvers
    for m in maneuvers:
        assert m.features is not None
        for key in CORE_FEATURES:
            assert key in m.features


def test_max_heel_lives_only_in_features():
    """max_heel_deg is no longer a Maneuver column — it's a feature only,
    reflecting the constant 12.0 heel of the synthetic IMU fixture."""
    gps = build_track()
    maneuvers = detect_maneuvers(gps, build_imu(gps), 0.0)
    assert maneuvers
    assert not hasattr(maneuvers[0], "max_heel_deg")
    for m in maneuvers:
        assert m.features["max_heel_deg"] == pytest.approx(12.0)


def test_max_heel_none_without_imu():
    gps = build_track()
    maneuvers = detect_maneuvers(gps, imu=None, twd_deg=0.0)
    assert maneuvers
    for m in maneuvers:
        assert m.features["max_heel_deg"] is None


# --------------------------------------------------------------------------- #
# Classifier registry (mirrors the wind_estimation registry tests)
# --------------------------------------------------------------------------- #

def test_registry_shape():
    assert ACTIVE_CLASSIFIER == "geometric"
    assert set(CLASSIFIERS) == {"geometric"}
    assert CLASSIFIERS[ACTIVE_CLASSIFIER] is geometric_classifier


def test_geometric_classifier_labels():
    tack = ManeuverCandidate(0, 5, 5, -90, 6, 6, 6, 1,
                             features={"rel_before": 45.0, "rel_after": -45.0})
    gybe = ManeuverCandidate(0, 5, 5, 160, 6, 6, 6, 1,
                             features={"rel_before": 150.0, "rel_after": -150.0})
    assert classify_maneuver(tack) == ManeuverType.TACK
    assert classify_maneuver(gybe) == ManeuverType.GYBE
    # never rejects or emits the third class
    assert geometric_classifier(tack) is not None


# --------------------------------------------------------------------------- #
# ML seam is dormant
# --------------------------------------------------------------------------- #

def test_ml_stub_is_not_registered_and_raises():
    assert _ml_classifier not in CLASSIFIERS.values()
    with pytest.raises(NotImplementedError):
        _ml_classifier(ManeuverCandidate(0, 5, 5, -90, 6, 6, 6, 1,
                                         features={"rel_before": 45.0, "rel_after": -45.0}))
    with pytest.raises(NotImplementedError):
        _load_maneuver_model()


# --------------------------------------------------------------------------- #
# Stage 2 can reject (false alarm) and can label the third class
# --------------------------------------------------------------------------- #

def test_false_alarm_drops_candidate(monkeypatch):
    """A classifier returning None removes the candidate entirely."""
    monkeypatch.setattr("processing.maneuvers.classify_maneuver", lambda cand: None)
    gps = build_track()
    assert detect_maneuvers(gps, build_imu(gps), 0.0) == []


def test_course_change_flows_through(monkeypatch):
    """A classifier emitting COURSE_CHANGE yields maneuvers of that type
    (proves the third class is reachable end-to-end in the worker)."""
    monkeypatch.setattr("processing.maneuvers.classify_maneuver",
                        lambda cand: ManeuverType.COURSE_CHANGE)
    gps = build_track()
    maneuvers = detect_maneuvers(gps, build_imu(gps), 0.0)
    assert maneuvers
    assert all(m.maneuver_type == ManeuverType.COURSE_CHANGE for m in maneuvers)


# --------------------------------------------------------------------------- #
# Filter ordering: classification precedes and gates the per-type min-change
# --------------------------------------------------------------------------- #

def _candidate(heading_change):
    return ManeuverCandidate(
        start_time=0, end_time=5, duration_sec=5, heading_change_deg=heading_change,
        speed_before_kts=6, speed_min_kts=6, speed_after_kts=6, recovery_time_sec=1,
        features={"rel_before": 45.0, "rel_after": -45.0},
    )


def test_min_change_gate_depends_on_type():
    # 30° change: below the tack floor (40°) but above the gybe floor (20°).
    cand = _candidate(30.0)
    assert _finalize(cand, ManeuverType.TACK) is None
    gybe = _finalize(cand, ManeuverType.GYBE)
    assert gybe is not None and gybe.maneuver_type == ManeuverType.GYBE


# --------------------------------------------------------------------------- #
# Configurable feature schema
# --------------------------------------------------------------------------- #

def _feature_ctx(true_wind=None):
    # A short pre/event/post window around a tack at t=10.
    gps = []
    for i in range(21):
        h = 45 if i < 10 else -45
        gps.append(GpsPoint(timestamp=float(i), lat=45.0, lon=9.0, speed_kts=6.0,
                            heading_deg=h % 360))
    return FeatureContext(
        gps=gps, imu=None, true_wind=true_wind, axis_deg=0.0, had_wind_axis=True,
        t_start=9.0, t_end=11.0, heading_before=45.0, heading_after=-45.0,
        speed_before_kts=6.0, speed_min_kts=6.0, speed_after_kts=6.0,
        recovery_time_sec=1.0, rel_before=45.0, rel_after=-45.0, window_sec=8.0,
    )


def test_extract_features_respects_enabled():
    ctx = _feature_ctx()
    out = extract_features(ctx, enabled=("speed_pre_mean",))
    # core features always present + the one enabled + schema version
    assert set(out) == set(CORE_FEATURES) | {"speed_pre_mean", "_schema_version"}
    assert out["speed_pre_mean"] == pytest.approx(6.0)


def test_twa_vmg_features_need_true_wind():
    without = extract_features(_feature_ctx(true_wind=None))
    assert without["twa_pre_mean"] is None
    assert without["vmg_pre_mean"] is None

    gps_ts = [float(i) for i in range(21)]
    tw = [{"timestamp": t, "twd_deg": 0.0, "tws_kts": 12.0} for t in gps_ts]
    with_wind = extract_features(_feature_ctx(true_wind=tw))
    assert with_wind["twa_pre_mean"] == pytest.approx(45.0)
    assert with_wind["twa_sign_change"] == 1.0  # crossed the wind
    assert with_wind["vmg_pre_mean"] == pytest.approx(6.0 * math.cos(math.radians(45)))


def test_default_enabled_is_all_registered():
    assert set(ENABLED_FEATURES) == set(FEATURE_EXTRACTORS)


def test_detect_candidates_metrics_match_finalize():
    """Stage 1 candidates carry the raw metrics that _finalize rounds into the
    Maneuver — a sanity check on the split."""
    gps = build_track()
    candidates = _detect_candidates(gps, build_imu(gps), 0.0)
    assert candidates
    for c in candidates:
        assert c.features["rel_before"] is not None
        assert c.duration_sec == c.end_time - c.start_time
