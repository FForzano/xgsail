"""Point fusion of one wind_cache.json waypoint (``xgsail_windfusion.waypoint``)
— the estimate the worker evaluates along a whole track and the backend at a
single point/time. Pure Python, no numpy: runs in the backend image too."""

import math
from datetime import datetime, timedelta, timezone

import pytest

import xgsail_windfusion as wf

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
E0 = T0.timestamp()


def _diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _waypoint(when=lambda dt: T0 + timedelta(seconds=dt)):
    """A station, two models and a grid estimate, timestamps built by ``when``."""
    return {
        "lat": 44.8, "lng": 12.3,
        "real_stations": [
            {"station_id": 7, "distance_km": 4.0, "observed_at": when(0), "twd_deg": 350.0,
             "tws_kts": 10.0, "gust_kts": 14.0},
            {"station_id": 7, "distance_km": 4.0, "observed_at": when(3600), "twd_deg": 10.0,
             "tws_kts": 12.0, "gust_kts": 16.0},
        ],
        "model_candidates": {
            "icon_d2": [{"observed_at": when(0), "twd_deg": 20.0, "tws_kts": 8.0},
                        {"observed_at": when(3600), "twd_deg": 30.0, "tws_kts": 9.0}],
            "gfs_seamless": [{"observed_at": when(-3600), "twd_deg": 0.0, "tws_kts": 7.0},
                             {"observed_at": when(7200), "twd_deg": 0.0, "tws_kts": 7.0}],
        },
        "grid_estimates": [{"time_bucket": when(0), "twd_deg": 5.0, "tws_kts": 11.0,
                            "gust_kts": None, "confidence": 0.5},
                           {"time_bucket": when(1800), "twd_deg": 5.0, "tws_kts": 11.0,
                            "gust_kts": None, "confidence": 0.5}],
        "track_observations": [],
    }


@pytest.mark.parametrize("when", [
    lambda dt: T0 + timedelta(seconds=dt),                           # datetime (backend)
    lambda dt: (T0 + timedelta(seconds=dt)).isoformat(),             # ISO string (worker JSON)
    lambda dt: (T0 + timedelta(seconds=dt)).isoformat().replace("+00:00", "Z"),
    lambda dt: E0 + dt,                                              # epoch float
    lambda dt: (T0 + timedelta(seconds=dt)).replace(tzinfo=None),    # naive = UTC
])
def test_every_timestamp_type_fuses_identically(when):
    reference = wf.fuse_waypoint(_waypoint(), E0 + 900)
    fused = wf.fuse_waypoint(_waypoint(when), E0 + 900)
    assert fused == reference


@pytest.mark.parametrize("t", [E0 + 900, T0 + timedelta(seconds=900),
                               (T0 + timedelta(seconds=900)).isoformat()])
def test_target_time_accepts_every_type(t):
    assert wf.fuse_waypoint(_waypoint(), t) == wf.fuse_waypoint(_waypoint(), E0 + 900)


def test_fuses_in_vector_space_and_reports_every_contribution():
    fused = wf.fuse_waypoint(_waypoint(), E0 + 900)
    assert _diff(fused.twd_deg, 5.0) < 15  # 350..30 around north, never ~180
    assert 7.0 <= fused.tws_kts <= 12.0
    names = {(c[0], c[1]) for c in fused.contributions}
    assert names == {("real_station", 7), ("model_regional", "icon_d2"),
                     ("model_global", "gfs_seamless"), ("grid_estimate", None)}
    assert fused.confidence == pytest.approx(sum(c[2] for c in fused.contributions))
    station_w = wf.source_weight("real_station", distance_km=4.0)
    assert ("real_station", 7, station_w) in fused.contributions


def test_station_name_is_preferred_over_its_id():
    wp = _waypoint()
    for r in wp["real_stations"]:
        r["station_name"] = "Lido"
    names = [c[1] for c in wf.fuse_waypoint(wp, E0).contributions if c[0] == "real_station"]
    assert names == ["Lido"]


def test_a_source_never_extrapolates_past_its_span():
    # 2 h in: only gfs_seamless (-1 h .. +2 h) still covers it.
    fused = wf.fuse_waypoint(_waypoint(), E0 + 7200)
    assert [c[1] for c in fused.contributions] == ["gfs_seamless"]
    assert _diff(fused.twd_deg, 0.0) < 1e-9
    assert fused.tws_kts == pytest.approx(7.0)
    assert fused.gust_kts is None
    # Outside every source's span there is nothing to report.
    assert wf.fuse_waypoint(_waypoint(), E0 + 7201) is None
    assert wf.fuse_waypoint(_waypoint(), E0 - 3601) is None


def test_gust_is_the_fused_mean_times_the_weighted_gust_factor():
    fused = wf.fuse_waypoint(_waypoint(), E0 + 1800)
    # Only the station reports gusts: 15 kn on an 11 kn mean, applied to the fused mean.
    assert fused.gust_kts == pytest.approx(fused.tws_kts * 15.0 / 11.0)

    wp = _waypoint()
    wp["grid_estimates"] = [dict(g, gust_kts=20.0) for g in wp["grid_estimates"]]
    fused = wf.fuse_waypoint(wp, E0 + 1800)
    w_station = wf.source_weight("real_station", distance_km=4.0)
    w_grid = (wf.source_weight("grid_estimate", internal_confidence=0.5)
              * (1.0 - wf.measurement_dominance(4.0)))
    factor = (15.0 / 11.0 * w_station + 20.0 / 11.0 * w_grid) / (w_station + w_grid)
    assert fused.gust_kts == pytest.approx(fused.tws_kts * factor)


def test_interpolates_direction_on_the_circle():
    # Station 350 -> 10 over an hour: halfway is north, not 180.
    wp = {"real_stations": _waypoint()["real_stations"]}
    fused = wf.fuse_waypoint(wp, E0 + 1800)
    assert _diff(fused.twd_deg, 0.0) < 1e-6
    assert fused.tws_kts == pytest.approx(11.0)  # speed interpolates linearly


def test_stations_are_weighted_separately_not_interleaved():
    rows = [
        {"station_id": "near", "distance_km": 2.0, "observed_at": E0, "twd_deg": 10.0, "tws_kts": 10.0},
        {"station_id": "far", "distance_km": 45.0, "observed_at": E0, "twd_deg": 200.0, "tws_kts": 10.0},
    ]
    fused = wf.fuse_waypoint({"real_stations": rows}, E0)
    assert len(fused.contributions) == 2
    assert _diff(fused.twd_deg, 10.0) < 10


def test_legacy_rows_without_station_id_group_by_coordinates():
    rows = [{"station_lat": 45.0, "station_lng": 12.0, "distance_km": 3.0,
             "observed_at": E0 + dt, "twd_deg": 90.0, "tws_kts": 8.0} for dt in (0, 3600)]
    fused = wf.fuse_waypoint({"real_stations": rows}, E0 + 60)
    assert len(fused.contributions) == 1


def test_a_calm_station_prevails_over_disagreeing_models_right_on_top_of_it():
    # Regression: standing right on a station reading 0.2 kt while every
    # Open-Meteo model (queried with no spatial offset, so they'd otherwise
    # carry full weight regardless of distance) disagrees at 5 kt used to
    # fuse to ~2.5 kt — the models' summed weight nearly matched the
    # station's. At distance ~0 the station must now dominate instead.
    wp = {
        "real_stations": [{"station_id": 1, "distance_km": 0.05, "observed_at": E0,
                           "twd_deg": 180.0, "tws_kts": 0.2}],
        "model_candidates": {
            "icon_d2": [{"observed_at": E0, "twd_deg": 180.0, "tws_kts": 5.0}],
            "icon_eu": [{"observed_at": E0, "twd_deg": 180.0, "tws_kts": 5.0}],
            "gfs_seamless": [{"observed_at": E0, "twd_deg": 180.0, "tws_kts": 5.0}],
            "ecmwf_ifs025": [{"observed_at": E0, "twd_deg": 180.0, "tws_kts": 5.0}],
        },
        "grid_estimates": [{"time_bucket": E0, "twd_deg": 180.0, "tws_kts": 5.0,
                            "gust_kts": None, "confidence": 1.0}],
        "track_observations": [],
    }
    fused = wf.fuse_waypoint(wp, E0)
    assert fused.tws_kts < 1.5  # close to the station's 0.2, not the models' 5.0


def test_unknown_model_is_weighed_as_global():
    rows = [{"observed_at": E0, "twd_deg": 90.0, "tws_kts": 8.0}]
    fused = wf.fuse_waypoint({"model_candidates": {"some_new_model": rows}}, E0)
    assert fused.contributions == (("model_global", "some_new_model", wf.SOURCE_PRIORS["model_global"]),)


def test_rows_without_a_usable_time_or_value_are_ignored():
    rows = [{"observed_at": "not a date", "twd_deg": 90.0, "tws_kts": 8.0},
            {"observed_at": None, "twd_deg": 90.0, "tws_kts": 8.0},
            {"observed_at": E0, "twd_deg": None, "tws_kts": 8.0}]
    assert wf.fuse_waypoint({"model_candidates": {"icon_d2": rows}}, E0) is None
    assert wf.fuse_waypoint({}, E0) is None
    assert wf.fuse_waypoint(_waypoint(), "garbage") is None


# --- blend_direction ------------------------------------------------------------

def _obs(twd, *, t=E0, lat=44.8, lng=12.3, confidence=0.95):
    return {"observed_at": t, "lat": lat, "lng": lng, "twd_deg": twd, "confidence": confidence}


def test_blend_pulls_toward_nearby_observations():
    assert _diff(wf.blend_direction(30.0, 1.9, 44.8, 12.3, E0, [_obs(0.0)] * 5), 0.0) < 10


def test_blend_is_local_in_space_and_time():
    far = wf.blend_direction(30.0, 1.9, 44.8, 12.3, E0, [_obs(0.0, lat=44.9)])  # ~11 km
    late = wf.blend_direction(30.0, 1.9, 44.8, 12.3, E0 + 3600, [_obs(0.0)])
    near = wf.blend_direction(30.0, 1.9, 44.8, 12.3, E0, [_obs(0.0)])
    assert _diff(far, 30.0) < 0.5 and _diff(late, 30.0) < 1.0
    assert _diff(near, 30.0) > 5.0


def test_blend_weights_match_source_weight():
    own = 1.0
    w = wf.source_weight("gps_tack", distance_km=0.0, dt_seconds=0.0, internal_confidence=0.95)
    expected = wf.weighted_wind_mean([(30.0, 1.0, own), (0.0, 1.0, w)])[0]
    assert wf.blend_direction(30.0, own, 44.8, 12.3, E0, [_obs(0.0)]) == pytest.approx(expected)


def test_blend_accepts_datetime_and_iso_times_and_wraps_north():
    obs = [_obs(350.0, t=T0.isoformat())] * 20
    assert _diff(wf.blend_direction(10.0, 1.0, 44.8, 12.3, T0, obs), 350.0) < 3


def test_blend_without_weight_or_observations_is_a_no_op():
    assert wf.blend_direction(42.0, 1.0, 44.8, 12.3, E0, []) == pytest.approx(42.0)
    assert wf.blend_direction(42.0, 0.0, 44.8, 12.3, E0, [_obs(0.0, t="bad")]) == 42.0


# --- hold_latest_seconds ---------------------------------------------------

def test_hold_latest_seconds_defaults_to_no_extrapolation():
    wp = {"real_stations": [{"station_id": 1, "distance_km": 2.0, "observed_at": E0,
                             "twd_deg": 10.0, "tws_kts": 8.0}]}
    assert wf.fuse_waypoint(wp, E0 + 1200) is None  # byte-identical to before this param existed


def test_hold_latest_seconds_holds_a_stale_source_with_decayed_weight():
    wp = {"real_stations": [{"station_id": 1, "distance_km": 2.0, "observed_at": E0,
                             "twd_deg": 10.0, "tws_kts": 8.0}]}
    gap = 1200.0
    fused = wf.fuse_waypoint(wp, E0 + gap, hold_latest_seconds=3600)
    assert fused is not None
    assert _diff(fused.twd_deg, 10.0) < 1e-9
    base_weight = wf.source_weight("real_station", distance_km=2.0)
    assert fused.confidence == pytest.approx(base_weight * math.exp(-gap / wf.TIME_DECAY_SECONDS))
    # Beyond the hold window, it's back to nothing.
    assert wf.fuse_waypoint(wp, E0 + 4000, hold_latest_seconds=3600) is None


def test_hold_latest_seconds_does_not_affect_a_source_still_ahead_of_t():
    wp = {"real_stations": [{"station_id": 1, "distance_km": 2.0, "observed_at": E0 + 3600,
                             "twd_deg": 10.0, "tws_kts": 8.0}]}
    # t is before the source's only reading — holding is only ever forward.
    assert wf.fuse_waypoint(wp, E0, hold_latest_seconds=3600) is None


def test_haversine_km():
    assert wf.haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.19, abs=0.01)
    assert wf.haversine_km(44.8, 12.3, 44.8, 12.3) == 0.0


def _station_vs_models(distance_km, station_rows=None):
    """A station reading 0.2 kt from the south against two models and a grid
    estimate agreeing on 12 kt from the north — the case where averaging the
    station in is exactly the wrong answer."""
    rows = station_rows or [{"station_id": 1, "distance_km": distance_km, "observed_at": E0 + dt,
                             "twd_deg": 180.0, "tws_kts": 0.2} for dt in (0, 3600)]
    flat = [{"observed_at": E0 + dt, "twd_deg": 0.0, "tws_kts": 12.0} for dt in (0, 3600)]
    return {"real_stations": rows,
            "model_candidates": {"icon_d2": flat, "gfs_seamless": flat},
            "grid_estimates": [{"time_bucket": E0 + dt, "twd_deg": 0.0, "tws_kts": 12.0,
                                "confidence": 1.0} for dt in (0, 3600)]}


def test_a_nearby_station_is_the_wind_not_one_vote_in_an_average():
    fused = wf.fuse_waypoint(_station_vs_models(wf.STATION_DOMINANCE_FULL_KM), E0 + 1800)
    assert fused.twd_deg == pytest.approx(180.0)
    assert fused.tws_kts == pytest.approx(0.2)
    # Silenced models are not reported as contributors (the live badge lists them).
    assert [c[0] for c in fused.contributions] == ["real_station"]


def test_station_dominance_fades_smoothly_with_distance():
    assert wf.measurement_dominance(0.0) == 1.0
    assert wf.measurement_dominance(wf.STATION_DOMINANCE_FADE_KM) == 0.0
    assert wf.measurement_dominance(None) == 0.0
    off = wf.WeightConfig(station_dominance_full_km=0.0, station_dominance_fade_km=0.0)
    assert wf.measurement_dominance(0.0, off) == 0.0
    ds = [wf.STATION_DOMINANCE_FULL_KM + k * 0.5 for k in range(20)]
    values = [wf.measurement_dominance(d) for d in ds]
    assert values == sorted(values, reverse=True)

    speeds = [wf.fuse_waypoint(_station_vs_models(d), E0 + 1800).tws_kts for d in (2.0, 7.5, 20.0)]
    assert speeds[0] == pytest.approx(0.2)
    assert speeds[0] < speeds[1] < speeds[2]


def test_far_station_is_weighed_exactly_as_before():
    fused = wf.fuse_waypoint(_station_vs_models(wf.STATION_DOMINANCE_FADE_KM), E0 + 1800)
    w_station = wf.source_weight("real_station", distance_km=wf.STATION_DOMINANCE_FADE_KM)
    assert dict(((c[0], c[1]), c[2]) for c in fused.contributions)[("real_station", 1)] \
        == pytest.approx(w_station)
    assert {c[0] for c in fused.contributions} == {"real_station", "model_regional",
                                                    "model_global", "grid_estimate"}


def test_models_come_back_across_a_station_data_gap():
    rows = [{"station_id": 1, "distance_km": 1.0, "observed_at": E0, "twd_deg": 180.0,
             "tws_kts": 0.2}]
    fused = wf.fuse_waypoint(_station_vs_models(1.0, rows), E0 + 1800)
    assert fused.tws_kts == pytest.approx(12.0)


def test_a_stale_live_reading_only_partly_silences_the_models():
    rows = [{"station_id": 1, "distance_km": 1.0, "observed_at": E0 + dt, "twd_deg": 180.0,
             "tws_kts": 0.2} for dt in (-600, 0)]
    gap = wf.TIME_DECAY_SECONDS  # last reading 30 min old
    fused = wf.fuse_waypoint(_station_vs_models(1.0, rows), E0 + gap, hold_latest_seconds=3600)
    weights = {c[1]: c[2] for c in fused.contributions}
    freshness = math.exp(-1.0)
    assert weights[1] == pytest.approx(wf.source_weight("real_station", distance_km=1.0) * freshness)
    assert weights["icon_d2"] == pytest.approx(wf.source_weight("model_regional") * (1.0 - freshness))


def _flat(tws, gust, **extra):
    return [dict({"observed_at": E0 + dt, "twd_deg": 0.0, "tws_kts": tws, "gust_kts": gust},
                 **extra) for dt in (0, 3600)]


def test_a_gust_never_reads_below_the_mean_wind():
    # A model reporting a gust below its own mean is bad data, not a lull.
    wp = {"real_stations": _flat(15.0, None, station_id=1, distance_km=20.0),
          "model_candidates": {"icon_d2": _flat(8.0, 7.0)}}
    fused = wf.fuse_waypoint(wp, E0 + 1800)
    assert fused.gust_kts == pytest.approx(fused.tws_kts)


def test_a_lone_station_gust_is_reported_exactly():
    wp = {"real_stations": _flat(10.0, 17.0, station_id=1, distance_km=6.0)}
    fused = wf.fuse_waypoint(wp, E0 + 1800)
    assert fused.tws_kts == pytest.approx(10.0)
    assert fused.gust_kts == pytest.approx(17.0)


def test_a_gustless_nearby_station_does_not_inherit_a_models_absolute_gust():
    # Regression: the station dominated the mean, but the model's residual weight
    # was renormalised to 100% of the gust, so 8 kn of wind read as gusting 22.
    wp = {"real_stations": _flat(8.0, None, station_id=1, distance_km=5.0),
          "model_candidates": {"icon_d2": _flat(15.0, 22.0)}}
    fused = wf.fuse_waypoint(wp, E0 + 1800)
    assert 0.0 < wf.measurement_dominance(5.0) < 1.0
    assert fused.tws_kts < 10.0
    assert fused.gust_kts == pytest.approx(fused.tws_kts * 22.0 / 15.0)
    assert abs(fused.gust_kts - fused.tws_kts * 22.0 / 15.0) < abs(fused.gust_kts - 22.0) / 10


def test_a_fully_dominant_station_without_gust_silences_the_models_gust():
    wp = {"real_stations": _flat(8.0, None, station_id=1,
                                 distance_km=wf.STATION_DOMINANCE_FULL_KM),
          "model_candidates": {"icon_d2": _flat(15.0, 22.0)}}
    assert wf.fuse_waypoint(wp, E0 + 1800).gust_kts is None


def test_no_gust_reporting_source_means_no_gust():
    wp = {"real_stations": _flat(8.0, None, station_id=1, distance_km=20.0),
          "model_candidates": {"icon_d2": _flat(15.0, None)}}
    assert wf.fuse_waypoint(wp, E0 + 1800).gust_kts is None


def test_a_near_calm_source_is_left_out_of_the_gust_factor():
    # 0.3 kn with a 4 kn gust would be a factor of ~13 on the model's 12 kn.
    wp = {"real_stations": _flat(0.3, 4.0, station_id=1, distance_km=20.0),
          "model_candidates": {"icon_d2": _flat(12.0, 15.0)}}
    fused = wf.fuse_waypoint(wp, E0 + 1800)
    assert fused.gust_kts == pytest.approx(fused.tws_kts * 15.0 / 12.0)
    # Alone, a calm station has no usable factor at all.
    calm = {"real_stations": _flat(0.3, 4.0, station_id=1, distance_km=20.0)}
    assert wf.fuse_waypoint(calm, E0 + 1800).gust_kts is None


def test_models_only_gust_combines_the_models_consistently():
    wp = {"model_candidates": {"icon_d2": _flat(10.0, 15.0), "gfs_seamless": _flat(20.0, 26.0)}}
    fused = wf.fuse_waypoint(wp, E0 + 1800)
    w_a, w_b = wf.source_weight("model_regional"), wf.source_weight("model_global")
    assert fused.tws_kts == pytest.approx((10.0 * w_a + 20.0 * w_b) / (w_a + w_b))
    factor = (1.5 * w_a + 1.3 * w_b) / (w_a + w_b)
    assert fused.gust_kts == pytest.approx(fused.tws_kts * factor)
    assert 15.0 < fused.gust_kts < 26.0
