"""Speed despiking (``processing/despike.py``): a single impossible GPS
speed sample must go, and a genuine acceleration must survive. The
false-positive test (``TestGenuineAcceleration``) is the important one —
eating a real planing burst is worse than keeping a spike."""

from processing.despike import despike_speed, record_speed

T0 = 1_800_000_000.0


def _track(speeds, key="speed_kn", dt=1.0, t0=T0):
    return [
        {"t": t0 + i * dt, "lat": 45.0 + 0.0001 * i, "lon": 9.0 + 0.0001 * i,
         key: s, "course": 45.0, "fix": 3}
        for i, s in enumerate(speeds)
    ]


class TestReferenceCase:
    """A ~4 kn track with one 23.4 kn sample in the middle (the observed bug:
    session averaging 3.9 kn, max_speed_kts reported as 23.4)."""

    def test_drops_exactly_the_spike(self):
        speeds = [3.9, 4.1, 3.8, 4.0, 4.2, 3.9, 23.4, 4.0, 3.8, 4.1, 3.9, 4.0]
        records = _track(speeds)
        cleaned, dropped = despike_speed(records)
        assert dropped == 1
        assert len(cleaned) == len(records) - 1
        assert 23.4 not in [r["speed_kn"] for r in cleaned]
        # Everything else is passed through untouched, same objects.
        assert cleaned == [r for r in records if r["speed_kn"] != 23.4]

    def test_second_pass_drops_nothing(self):
        records = _track([3.9, 4.1, 3.8, 4.0, 4.2, 3.9, 23.4, 4.0, 3.8, 4.1, 3.9, 4.0])
        cleaned, _ = despike_speed(records)
        again, dropped = despike_speed(cleaned)
        assert dropped == 0
        assert again is cleaned


class TestGenuineAcceleration:
    def test_sustained_ramp_is_kept(self):
        """A dinghy powering up 4 -> 12 kn over several seconds: every sample
        agrees with the one after it, so none is a spike."""
        records = _track([4.0, 4.2, 4.1, 6.0, 9.0, 12.0, 12.4, 12.1, 11.8, 12.0])
        cleaned, dropped = despike_speed(records)
        assert dropped == 0
        assert cleaned is records

    def test_hard_acceleration_and_deceleration_kept(self):
        """Planing burst then a bear-away back down — big changes, but each
        one sustained across consecutive samples."""
        records = _track([3.0, 3.2, 7.0, 11.0, 14.0, 14.2, 13.8, 10.0, 6.0, 3.5, 3.2])
        _, dropped = despike_speed(records)
        assert dropped == 0

    def test_first_sample_of_an_acceleration_is_not_dropped(self):
        """A one-sided check would reject index 2 here; the both-neighbours
        rule must not."""
        records = _track([2.0, 2.0, 9.0, 16.0, 22.0, 24.0])
        _, dropped = despike_speed(records)
        assert dropped == 0


class TestCleanTracks:
    def test_clean_track_unchanged(self):
        records = _track([5.0, 5.2, 4.9, 5.1, 5.3, 5.0, 4.8, 5.1])
        cleaned, dropped = despike_speed(records)
        assert dropped == 0
        assert cleaned is records

    def test_normal_gps_jitter_is_kept(self):
        speeds = [4.0, 4.6, 3.5, 4.4, 3.7, 4.5, 3.6, 4.3, 3.9, 4.2, 3.8, 4.4]
        _, dropped = despike_speed(_track(speeds))
        assert dropped == 0


class TestSafetyCap:
    def test_mostly_noise_drops_nothing(self):
        """A track that is 30% 'spiky' means the thresholds don't fit the
        data — deleting a third of somebody's session is not acceptable."""
        speeds = []
        for i in range(60):
            speeds.append(30.0 if i % 3 == 1 else 4.0)
        records = _track(speeds)
        cleaned, dropped = despike_speed(records)
        assert dropped == 0
        assert cleaned is records

    def test_cap_is_configurable_and_enforced(self):
        """3 spikes in 200 samples (1.5%) is under the default cap; tighten
        the cap and the same track is left alone."""
        speeds = [4.0 + 0.1 * (i % 3) for i in range(200)]
        for i in (40, 90, 150):
            speeds[i] = 25.0
        records = _track(speeds)
        assert despike_speed(records)[1] == 3
        assert despike_speed(records, max_drop_fraction=0.001, min_drop_allowance=0)[1] == 0


class TestDegenerateInput:
    def test_short_tracks(self):
        for n in range(3):
            records = _track([20.0] * n)
            assert despike_speed(records) == (records, 0)

    def test_missing_and_none_speeds(self):
        records = [
            {"t": T0 + 0, "speed_kn": 4.0},
            {"t": T0 + 1},
            {"t": T0 + 2, "speed_kn": None},
            {"t": T0 + 3, "speed_kn": 4.1},
            {"t": T0 + 4, "speed_kn": 25.0},
            {"t": T0 + 5, "speed_kn": 4.0},
            {"t": T0 + 6, "speed_kn": 3.9},
        ]
        cleaned, dropped = despike_speed(records)
        assert dropped == 1
        assert all(r.get("speed_kn") != 25.0 for r in cleaned)

    def test_duplicate_and_non_monotonic_timestamps(self):
        records = [
            {"t": T0, "speed_kn": 4.0},
            {"t": T0, "speed_kn": 4.1},
            {"t": T0 + 1, "speed_kn": 4.0},
            {"t": T0 + 1, "speed_kn": 3.9},
            {"t": T0 + 0.5, "speed_kn": 4.2},
            {"t": T0 + 2, "speed_kn": 4.0},
        ]
        cleaned, dropped = despike_speed(records)
        assert dropped == 0
        assert cleaned is records

    def test_zero_dt_around_a_spike_still_caught_by_hampel(self):
        records = [{"t": T0, "speed_kn": 4.0}, {"t": T0, "speed_kn": 4.1},
                   {"t": T0, "speed_kn": 23.4}, {"t": T0, "speed_kn": 4.0},
                   {"t": T0, "speed_kn": 3.9}, {"t": T0, "speed_kn": 4.1}]
        cleaned, dropped = despike_speed(records)
        assert dropped == 1
        assert all(r["speed_kn"] != 23.4 for r in cleaned)

    def test_iso_timestamps(self):
        speeds = [4.0, 4.1, 3.9, 23.4, 4.0, 3.8, 4.1]
        records = [{"timestamp": f"2026-04-02T10:00:{i:02d}Z", "speed_kts": s}
                   for i, s in enumerate(speeds)]
        _, dropped = despike_speed(records)
        assert dropped == 1

    def test_non_list_input(self):
        assert despike_speed(None) == (None, 0)


class TestSpeedKeyVariants:
    def test_speed_kn_and_speed_kts_and_speed(self):
        for key in ("speed_kn", "speed_kts", "speed"):
            records = _track([4.0, 4.1, 3.9, 4.0, 23.4, 4.0, 3.8, 4.1, 4.0], key=key)
            cleaned, dropped = despike_speed(records)
            assert dropped == 1, key
            assert all(r[key] != 23.4 for r in cleaned)

    def test_record_speed_reads_variants(self):
        assert record_speed({"speed_kts": 5}) == 5.0
        assert record_speed({"speed_kn": 5.5}) == 5.5
        assert record_speed({"speed": 2}) == 2.0
        assert record_speed({}) is None
        assert record_speed({"speed_kn": None}) is None
        assert record_speed({"speed_kn": "fast"}) is None


def test_unparseable_timestamp_does_not_disable_the_filter():
    """One corrupt timestamp must cost only its own sample the acceleration
    gate. `to_timestamp` raises on a malformed ISO string, and letting that
    escape would silently turn the despike off for the whole track."""
    speeds = [3.9, 4.1, 3.8, 4.0, 4.2, 3.9, 23.4, 4.0, 3.8, 4.1, 3.9, 4.0]
    records = [{"t": f"2026-06-01T10:00:{i:02d}Z", "speed_kn": s}
               for i, s in enumerate(speeds)]
    records[2]["t"] = "not-a-timestamp"

    filtered, dropped = despike_speed(records)

    assert dropped == 1
    assert 23.4 not in [r["speed_kn"] for r in filtered]
