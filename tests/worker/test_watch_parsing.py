"""Apple Watch companion parsing in the process_upload worker: the watch's
``watch_nav.csv`` GPS format (ISO timestamps, no clock correction) and the
shared ``process_scalar`` parser for the physiological streams
(heart_rate/energy/hrv/respiration). See docs/device-protocol.md."""

import sys
import types

# handler.py builds a real S3 client at import time (`s3 = _make_s3_client()`),
# which needs AWS credentials/profile we don't have in the test env. These
# tests are pure CSV parsing and never touch S3, so stub boto3 before import.
sys.modules['boto3'] = types.SimpleNamespace(client=lambda *a, **k: None)

import handler as h  # noqa: E402


# --- GPS: watch (ISO `t`) format --------------------------------------------

def test_watch_gps_no_clock_correction():
    """S1's -2460s correction must NOT apply to the watch — its `t` is already
    correct UTC. Regression guard: an ISO-`t` file with lat/lon must be
    detected as the watch format, not S1."""
    nav = (
        "t,lat,lon,speed_kn,course\n"
        "2026-07-24T14:05:03.000Z,43.12345,10.54321,6.42,182.5\n"
        "2026-07-24T14:05:04.000Z,43.12350,10.54330,6.80,180.0\n"
    )
    data_1hz, data_10hz, _actual_date, _drops = h.process_gps(nav)
    assert [p['t'] for p in data_1hz] == [
        "2026-07-24T14:05:03Z", "2026-07-24T14:05:04Z",
    ]
    assert data_1hz[0]['lat'] == 43.12345
    assert data_1hz[0]['speed_kn'] == 6.42
    assert data_1hz[0]['course'] == 182.5
    assert len(data_10hz) == 2


def test_watch_gps_1hz_keeps_max_speed_per_second():
    nav = (
        "t,lat,lon,speed_kn,course\n"
        "2026-07-24T14:05:03.000Z,43.1,10.5,6.4,182\n"
        "2026-07-24T14:05:03.500Z,43.1,10.5,7.9,181\n"
        "2026-07-24T14:05:04.000Z,43.1,10.5,6.8,180\n"
    )
    data_1hz, data_10hz, _d, _dr = h.process_gps(nav)
    assert len(data_1hz) == 2
    assert data_1hz[0]['speed_kn'] == 7.9  # max within the 14:05:03 second
    assert len(data_10hz) == 3


def test_e1_format_not_misdetected_as_watch():
    """An E1 file (`utc` + `gps_date`) must still take the E1 path even though
    it also has lat/lon — the watch branch only triggers on a `t` column."""
    e1 = (
        "ms,utc,lat,lon,alt,sog,cog,sat,hdop,fix,gps_date\n"
        "100,140503.100,43.123,10.543,0,6.4,182,9,0.8,1,240726\n"
    )
    data_1hz, _d10, _date, _drops = h.process_gps(e1)
    assert data_1hz and data_1hz[0]['t'].startswith("2026-07-24T14:05:03")


# --- Physiological scalar streams -------------------------------------------

def test_process_scalar_per_sensor():
    cases = {
        'heart_rate': ("bpm", "t,bpm\n2026-07-24T14:05:03Z,142\n2026-07-24T14:05:04Z,145\n", 142.0),
        'energy': ("kcal", "t,kcal\n2026-07-24T14:05:03Z,12.5\n", 12.5),
        'hrv': ("ms", "t,ms\n2026-07-24T14:05:00Z,48.2\n", 48.2),
        'respiration': ("brpm", "t,brpm\n2026-07-24T14:05:00Z,18.0\n", 18.0),
    }
    for sensor, (col, csv, first_val) in cases.items():
        assert h.SCALAR_SENSOR_COLUMNS[sensor] == col
        out = h.process_scalar(csv, col)
        assert out[0]['t'] == "2026-07-24T14:05:03Z" if sensor in ("heart_rate", "energy") \
            else out[0]['t'] == "2026-07-24T14:05:00Z"
        assert out[0][col] == first_val


def test_process_scalar_skips_bad_rows():
    csv = (
        "t,bpm\n"
        "2026-07-24T14:05:03Z,142\n"
        ",150\n"              # missing timestamp
        "2026-07-24T14:05:05Z,\n"   # missing value
        "2026-07-24T14:05:06Z,notanumber\n"  # unparseable value
        "2026-07-24T14:05:07Z,148\n"
    )
    out = h.process_scalar(csv, "bpm")
    assert [r['bpm'] for r in out] == [142.0, 148.0]


# --- Filename routing -------------------------------------------------------

def test_sensor_from_filename_watch():
    assert h._sensor_from_filename("watch_nav.csv") == "gps"
    assert h._sensor_from_filename("watch_hr.csv") == "heart_rate"
    assert h._sensor_from_filename("watch_energy.csv") == "energy"
    assert h._sensor_from_filename("watch_hrv.csv") == "hrv"
    assert h._sensor_from_filename("watch_resp.csv") == "respiration"
