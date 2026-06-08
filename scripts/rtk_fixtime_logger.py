#!/usr/bin/env python3
"""rtk_fixtime_logger.py — side-by-side RTK fix-time logger for two GNSS rovers.

Logs PC-timestamped NMEA from TWO serial ports at once (e.g. LG290P quad-band
vs LC29HEAMD dual-band), parses GGA fix quality, and auto-extracts the
time-to-RTK-fixed (q=4) per trial — the metric that actually differs between
chips, unlike sat count / HDOP / fix-quality (see CLAUDE.md gotcha #3).

Workflow: feed BOTH receivers the SAME RTCM correction stream (NTRIP or your
LC29HEA base) with a separate tool (u-center / RTKLIB str2str). Run this logger
on both NMEA outputs. Press ENTER to mark a trial start (t0); the script then
reports, per chip, how long until it first reaches q=4:

  • corrections-on test : press ENTER the instant RTCM starts flowing
  • cold-start TTFF test : press ENTER at power-on (corrections already on)
  • re-acquisition test  : press ENTER when you UNCOVER the antenna
  • static-accuracy test : press ENTER once, then sit still — read 2D-RMS at exit

GGA field 6 (fix quality): 0 invalid · 1 autonomous · 2 DGPS · 4 RTK-FIXED ·
5 RTK-float · 6 dead-reckoning.

Run ~10 ENTER-marked trials per chip per environment; use a SEPARATE --out file
for open-sky vs multipath so you can compare medians. Requires: pip install pyserial

macOS: list ports with `ls /dev/tty.usb*`.

Example:
  python scripts/rtk_fixtime_logger.py \
      --port-a /dev/tty.usbserial-AAAA --label-a LG290P  --baud-a 460800 \
      --port-b /dev/tty.usbserial-BBBB --label-b LC29HEA --baud-b 115200 \
      --out rtk_opensky.csv
"""
import argparse
import csv
import math
import queue
import statistics
import sys
import threading
import time
from datetime import datetime, timezone

try:
    import serial  # pyserial
except ImportError:
    sys.exit("pyserial not installed — run: pip install pyserial")

Q_NAMES = {0: "invalid", 1: "auto", 2: "dgps", 4: "RTK-FIX", 5: "rtk-float", 6: "dr"}


def nmea_checksum_ok(line):
    if not line.startswith("$") or "*" not in line:
        return False
    body, _, cs = line[1:].partition("*")
    try:
        want = int(cs[:2], 16)
    except ValueError:
        return False
    got = 0
    for ch in body:
        got ^= ord(ch)
    return got == want


def _dm_to_deg(v, hemi):
    """NMEA ddmm.mmmm / dddmm.mmmm -> signed decimal degrees."""
    if not v:
        return None
    dot = v.find(".")
    if dot < 3:
        return None
    try:
        deg = float(v[: dot - 2])
        minutes = float(v[dot - 2:])
    except ValueError:
        return None
    dec = deg + minutes / 60.0
    return -dec if hemi in ("S", "W") else dec


def parse_gga(line):
    """Return dict(quality,sats,hdop,lat,lon) for a *GGA sentence, else None."""
    if "GGA" not in line:
        return None
    f = line.split(",")
    if len(f) < 10:
        return None
    try:
        q = int(f[6]) if f[6] != "" else 0
    except ValueError:
        return None
    try:
        hdop = float(f[8]) if f[8] else None
    except ValueError:
        hdop = None
    # Field 13 = age of differential/RTK corrections (s); field 14 = ref
    # station id (may carry the *checksum). High corr-age while q=5 (float)
    # is the signature of a slow/jittery correction link (e.g. the ESP-NOW
    # relay) — the usual reason a short-baseline rover won't reach q=4.
    age = None
    if len(f) > 13 and f[13] not in ("", None):
        try:
            age = float(f[13])
        except ValueError:
            age = None
    station = f[14].split("*")[0] if len(f) > 14 and f[14] else None
    return {
        "quality": q,
        "sats": int(f[7]) if f[7].isdigit() else None,
        "hdop": hdop,
        "lat": _dm_to_deg(f[2], f[3]),
        "lon": _dm_to_deg(f[4], f[5]),
        "age": age,
        "station": station,
    }


class ChipState:
    def __init__(self, label):
        self.label = label
        self.q = None
        self.total = 0
        self.q4 = 0
        self.drops = 0          # 4 -> non-4 transitions
        self.mark_t = None
        self.t_first_float = None
        self.t_first_fix = None
        self.ttff_list = []     # seconds mark -> first q4, per trial
        self.float_list = []    # seconds first-float -> first-fix, per trial
        self.lat_samples = []   # q4 positions since last mark (static scatter)
        self.lon_samples = []
        self.qcount = {}        # epochs per quality (1/4/5/...)
        self.age_float = []     # corr-age while q=5 (float)
        self.age_fix = []       # corr-age while q=4 (fixed)
        self.last_age = None    # most recent corr-age (for live status)

    def mark(self, t):
        self.mark_t = t
        self.t_first_float = None
        self.t_first_fix = None
        self.lat_samples = []
        self.lon_samples = []

    def update(self, t, gga):
        q = gga["quality"]
        prev = self.q
        self.q = q
        self.total += 1
        self.qcount[q] = self.qcount.get(q, 0) + 1
        age = gga.get("age")
        self.last_age = age
        if age is not None:
            if q == 5:
                self.age_float.append(age)
            elif q == 4:
                self.age_fix.append(age)
        if q == 4:
            self.q4 += 1
            if gga["lat"] is not None and gga["lon"] is not None:
                self.lat_samples.append(gga["lat"])
                self.lon_samples.append(gga["lon"])
        if prev == 4 and q != 4:
            self.drops += 1
        if self.mark_t is not None:
            if q == 5 and self.t_first_float is None:
                self.t_first_float = t
            if q == 4 and self.t_first_fix is None:
                self.t_first_fix = t
                ttff = t - self.mark_t
                self.ttff_list.append(ttff)
                fl = (t - self.t_first_float) if self.t_first_float else None
                if fl is not None:
                    self.float_list.append(fl)
                return ttff, fl
        return None


def reader(port, baud, label, bus, stop):
    # Open WITHOUT pulsing DTR/RTS, so we don't trip the ESP32 auto-reset
    # circuit — a reboot would clear the runtime `gpsraw` toggle and the
    # NMEA stream would stop. Setting dtr/rts on the not-yet-open port fixes
    # the initial line state so open() doesn't assert them. (Harmless for a
    # bare GNSS dev board too.)
    try:
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baud
        ser.timeout = 1
        ser.dtr = False
        ser.rts = False
        ser.open()
    except Exception as e:  # noqa: BLE001
        print(f"[{label}] cannot open {port}@{baud}: {e}")
        stop.set()
        return
    print(f"[{label}] open {port}@{baud} (no-reset)")
    while not stop.is_set():
        try:
            raw = ser.readline()
        except Exception as e:  # noqa: BLE001
            print(f"[{label}] read error: {e}")
            break
        if not raw:
            continue
        t = time.monotonic()
        s = raw.decode("ascii", "ignore").strip()
        if s:
            bus.put((t, label, s))
    ser.close()


def main():
    ap = argparse.ArgumentParser(description="Side-by-side RTK fix-time logger.")
    ap.add_argument("--port-a", required=True)
    ap.add_argument("--port-b", required=True)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--baud-a", type=int, default=115200)
    ap.add_argument("--baud-b", type=int, default=115200)
    ap.add_argument("--out", default="rtk_fixtime.csv")
    ap.add_argument("--check", action="store_true", help="require valid NMEA checksum")
    args = ap.parse_args()

    chips = {
        args.label_a: ChipState(args.label_a),
        args.label_b: ChipState(args.label_b),
    }
    bus = queue.Queue()
    stop = threading.Event()
    for port, baud, label in (
        (args.port_a, args.baud_a, args.label_a),
        (args.port_b, args.baud_b, args.label_b),
    ):
        threading.Thread(target=reader, args=(port, baud, label, bus, stop), daemon=True).start()

    trial = [0]

    def keywatch():
        for _ in sys.stdin:  # one mark per ENTER
            trial[0] += 1
            t = time.monotonic()
            for c in chips.values():
                c.mark(t)
            print(f"\n===== TRIAL {trial[0]} START (mark set) — timing to q=4 =====")

    threading.Thread(target=keywatch, daemon=True).start()

    f = open(args.out, "w", newline="")
    w = csv.writer(f)
    w.writerow(["iso", "mono", "trial", "chip", "quality", "qname",
                "sats", "hdop", "lat", "lon", "corr_age_s", "ref_sta", "since_mark_s"])
    print(f"Logging to {args.out}. Press ENTER to mark a trial start. Ctrl-C to stop + summary.\n")

    last_status = 0.0
    try:
        while not stop.is_set():
            try:
                t, label, s = bus.get(timeout=0.5)
            except queue.Empty:
                continue
            if args.check and not nmea_checksum_ok(s):
                continue
            gga = parse_gga(s)
            if gga is None:
                continue
            c = chips[label]
            since = (t - c.mark_t) if c.mark_t else None
            ev = c.update(t, gga)
            w.writerow([
                datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                f"{t:.3f}", trial[0], label, gga["quality"], Q_NAMES.get(gga["quality"], "?"),
                gga["sats"], gga["hdop"],
                f"{gga['lat']:.7f}" if gga["lat"] is not None else "",
                f"{gga['lon']:.7f}" if gga["lon"] is not None else "",
                f"{gga['age']:.1f}" if gga.get("age") is not None else "",
                gga.get("station") or "",
                f"{since:.2f}" if since is not None else "",
            ])
            if ev:
                ttff, fl = ev
                extra = f" (float->fix {fl:.1f}s)" if fl else ""
                print(f"  >>> {label}: RTK FIX (q=4) in {ttff:.1f}s from mark{extra}")
            now = time.monotonic()
            if now - last_status >= 1.0:
                last_status = now
                cells = []
                for lbl, cc in chips.items():
                    cur = Q_NAMES.get(cc.q, "-")
                    pct = (100 * cc.q4 / cc.total) if cc.total else 0
                    age = f" age={cc.last_age:.0f}s" if cc.last_age is not None else ""
                    cells.append(f"{lbl}:{cur} q4%={pct:.0f}{age}")
                print("  " + " | ".join(cells), end="\r")
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        f.close()
        print("\n\n================ SUMMARY ================")
        for lbl, c in chips.items():
            pct = (100 * c.q4 / c.total) if c.total else 0
            print(f"\n[{lbl}]  epochs={c.total}  q4%={pct:.1f}  drops(4->x)={c.drops}")
            if c.total:
                brk = "  ".join(
                    f"{Q_NAMES.get(q, q)}={100 * n / c.total:.0f}%"
                    for q, n in sorted(c.qcount.items())
                )
                print(f"  quality mix: {brk}")
            if c.age_float:
                print(f"  corr-age while FLOAT (q5): median={statistics.median(c.age_float):.1f}s "
                      f"max={max(c.age_float):.1f}s  <-- >2s here = correction link too slow/lossy")
            if c.age_fix:
                print(f"  corr-age while FIXED (q4): median={statistics.median(c.age_fix):.1f}s")
            if c.ttff_list:
                print(f"  TTFF->q4 per trial (s): {[round(x, 1) for x in c.ttff_list]}")
                print(f"    median={statistics.median(c.ttff_list):.1f}s  "
                      f"n={len(c.ttff_list)}  max={max(c.ttff_list):.1f}s")
            if c.float_list:
                print(f"  float->fix median={statistics.median(c.float_list):.1f}s")
            if len(c.lat_samples) > 5:
                mlat = statistics.mean(c.lat_samples)
                mlon = statistics.mean(c.lon_samples)
                mlat_m = 111320.0
                mlon_m = 111320.0 * math.cos(math.radians(mlat))
                ex = [(x - mlat) * mlat_m for x in c.lat_samples]
                ey = [(y - mlon) * mlon_m for y in c.lon_samples]
                rms = math.sqrt(statistics.fmean([a * a + b * b for a, b in zip(ex, ey)]))
                print(f"  static scatter (last trial, {len(c.lat_samples)} q4 fixes): "
                      f"2D-RMS={rms:.3f} m")
        print(f"\nRaw CSV: {args.out}")


if __name__ == "__main__":
    main()
