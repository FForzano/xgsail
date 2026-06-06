#!/usr/bin/env python3
"""
rtk_fix_summary.py — RTK fix-quality summary for SailFrames nav.csv logs.

After an RTK test drive, point this at the rover's nav.csv (or a session dir,
or a glob of them) to see how much of the track held RTK FIXED vs float/DGPS/
none — the headline number for "did the RTK relay hold while moving."

nav.csv columns (header-driven, so order-robust): ms,utc,lat,lon,alt,sog,cog,
sat,hdop,fix,gps_date. The `fix` column is the GGA fix-quality:
  4 = RTK FIXED (cm)   5 = RTK float   2 = DGPS/SBAS   1 = GPS   0 = no fix

Usage:
  scripts/rtk_fix_summary.py /Volumes/E6/sf/20260605_xxxx/E6_..._nav.csv
  scripts/rtk_fix_summary.py /Volumes/E6/sf/20260605_xxxx        # a session dir
  scripts/rtk_fix_summary.py "/Volumes/E6/sf/*/*_nav.csv"        # glob (quote it)
  scripts/rtk_fix_summary.py /Volumes/E6/sf --combined           # roll all up

No dependencies (stdlib only).
"""
import csv
import glob
import os
import sys

QUAL = {0: "no fix", 1: "GPS", 2: "DGPS/SBAS", 4: "RTK FIXED", 5: "RTK float"}
# print order (most-wanted first)
ORDER = [4, 5, 2, 1, 0]


def find_navs(arg):
    """Resolve a path/dir/glob into a list of *_nav.csv files."""
    if os.path.isdir(arg):
        return sorted(glob.glob(os.path.join(arg, "**", "*_nav.csv"), recursive=True)) \
            or sorted(glob.glob(os.path.join(arg, "*_nav.csv")))
    if any(c in arg for c in "*?["):
        return sorted(glob.glob(arg))
    return [arg] if os.path.isfile(arg) else []


def col_index(header, *names):
    """Find the first matching column index by name (case-insensitive)."""
    low = [h.strip().lower() for h in header]
    for n in names:
        if n in low:
            return low.index(n)
    return None


def analyze(path):
    with open(path, newline="") as f:
        rdr = csv.reader(f)
        try:
            header = next(rdr)
        except StopIteration:
            return None
        i_fix = col_index(header, "fix", "fix_quality")
        i_hdop = col_index(header, "hdop")
        i_ms = col_index(header, "ms")
        i_hacc = col_index(header, "hacc")   # GST horizontal 1-sigma (m), FW >= 2026.06.05.03
        if i_fix is None:
            return {"path": path, "error": "no 'fix' column in header"}

        counts = {}        # fix_quality -> row count
        hdop_fixed = []    # hdop samples while FIXED
        hacc_fixed = []    # GST horizontal 1-sigma (m) samples while FIXED
        first_ms = last_ms = None
        cur_streak = best_streak = 0
        total = 0

        for row in rdr:
            if len(row) <= i_fix:
                continue
            try:
                q = int(float(row[i_fix]))
            except ValueError:
                continue
            total += 1
            counts[q] = counts.get(q, 0) + 1
            if i_ms is not None and len(row) > i_ms:
                try:
                    ms = int(float(row[i_ms]))
                    if first_ms is None:
                        first_ms = ms
                    last_ms = ms
                except ValueError:
                    pass
            if q == 4:
                cur_streak += 1
                best_streak = max(best_streak, cur_streak)
                if i_hdop is not None and len(row) > i_hdop:
                    try:
                        hdop_fixed.append(float(row[i_hdop]))
                    except ValueError:
                        pass
                if i_hacc is not None and len(row) > i_hacc:
                    try:
                        v = float(row[i_hacc])
                        if v > 0:
                            hacc_fixed.append(v)
                    except ValueError:
                        pass
            else:
                cur_streak = 0

    dur_s = ((last_ms - first_ms) / 1000.0) if (first_ms is not None and last_ms is not None) else None
    return {
        "path": path, "total": total, "counts": counts, "dur_s": dur_s,
        "best_streak": best_streak,
        "hdop_fixed_mean": (sum(hdop_fixed) / len(hdop_fixed)) if hdop_fixed else None,
        "hacc_fixed_mean": (sum(hacc_fixed) / len(hacc_fixed)) if hacc_fixed else None,
        "hacc_fixed_max": max(hacc_fixed) if hacc_fixed else None,
        # assume ~10 Hz logging: streak samples -> seconds estimate
        "best_streak_s": (best_streak / 10.0) if best_streak else 0,
    }


def report(res):
    if res is None:
        return
    if "error" in res:
        print(f"  ! {res['path']}: {res['error']}")
        return
    total = res["total"]
    print(f"\n{os.path.basename(res['path'])}  ({total} fixes"
          + (f", {res['dur_s']:.0f}s" if res["dur_s"] else "") + ")")
    if total == 0:
        print("  (no data rows)")
        return
    for q in ORDER:
        n = res["counts"].get(q, 0)
        if n:
            bar = "#" * int(round(40 * n / total))
            print(f"  {QUAL[q]:>10}: {100*n/total:5.1f}%  ({n:6d})  {bar}")
    # any unexpected quality codes
    for q in sorted(res["counts"]):
        if q not in ORDER:
            n = res["counts"][q]
            print(f"  {('q='+str(q)):>10}: {100*n/total:5.1f}%  ({n:6d})  [unknown code]")
    fixed_pct = 100 * res["counts"].get(4, 0) / total
    print(f"  --> RTK FIXED {fixed_pct:.1f}% of the track"
          + (f"; longest FIXED run ~{res['best_streak_s']:.0f}s ({res['best_streak']} samples)" if res['best_streak'] else "")
          + (f"; mean HDOP@FIXED {res['hdop_fixed_mean']:.2f}" if res['hdop_fixed_mean'] else ""))
    if res.get("hacc_fixed_mean"):
        print(f"  --> accuracy@FIXED (GST 1sigma h): mean {res['hacc_fixed_mean']*100:.1f} cm, "
              f"worst {res['hacc_fixed_max']*100:.1f} cm")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    combined = "--combined" in argv
    if not args:
        print(__doc__)
        return 1
    files = []
    for a in args:
        files += find_navs(a)
    if not files:
        print("No *_nav.csv files found for:", args, file=sys.stderr)
        return 1

    results = [analyze(p) for p in files]
    for r in results:
        report(r)

    if combined and len([r for r in results if r and "counts" in r]) > 1:
        agg = {}
        tot = 0
        for r in results:
            if r and "counts" in r:
                tot += r["total"]
                for q, n in r["counts"].items():
                    agg[q] = agg.get(q, 0) + n
        print("\n==================== COMBINED ====================")
        report({"path": "ALL", "total": tot, "counts": agg, "dur_s": None,
                "best_streak": 0, "best_streak_s": 0, "hdop_fixed_mean": None})
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
