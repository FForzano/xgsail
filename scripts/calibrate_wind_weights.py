#!/usr/bin/env python3
"""Calibrate the wind-fusion reliability weights against real station data.

Leave-one-out: for each real fixed station, treat its observations as ground
truth and predict them by fusing every OTHER source (the other stations plus
the Open-Meteo models) at that station's location and time. Search a grid of
``WeightConfig`` values for the one that minimizes the mean direction error,
and print it as a suggested replacement for the shipped defaults in
``libs/xgsail_windfusion``.

This is the practical entry point for Fase 4; the pure evaluation/search core
lives in ``xgsail_windfusion.calibration`` (and is unit-tested). This
script only assembles real observations into that core's ``Site`` shape.

Run it with the backend environment configured (DB + network for Open-Meteo),
e.g. inside the backend container:

    python scripts/calibrate_wind_weights.py \
        --start 2026-06-01 --end 2026-06-30 --max-truth-per-station 20

It only reads (queries observations, fetches Open-Meteo); it writes nothing.
The result is a recommendation to apply by hand after reviewing the error.
"""

import argparse
from datetime import datetime, timedelta, timezone

from backend.repositories import get_repos
from backend.services.geo import haversine_m
from backend.services.wind_lookup import REAL_SENSOR_PROVIDERS
from backend.services.wind_providers import open_meteo
from xgsail_windfusion import DEFAULT_CONFIG
from xgsail_windfusion import calibration as cal

# Open-Meteo model name -> reliability class. Mirrors the worker's
# _MODEL_SOURCE_TYPE (workers/process_upload/processing/wind_estimation.py);
# both derive from open_meteo.MODEL_CANDIDATES (regional first, global last).
MODEL_RELIABILITY = {
    "icon_d2": "model_regional",
    "icon_eu": "model_regional",
    "gfs_seamless": "model_global",
    "ecmwf_ifs025": "model_global",
}

# Only fuse other stations within this range of the held-out one — a station on
# the far side of the region says little about it.
OTHER_STATION_MAX_KM = 80.0


def _nearest(rows, when, time_attr="observed_at"):
    """The row whose time is closest to ``when`` (rows: ORM objs or dicts)."""
    def t(r):
        return getattr(r, time_attr) if hasattr(r, time_attr) else r[time_attr]
    return min(rows, key=lambda r: abs((t(r) - when).total_seconds())) if rows else None


def _model_contributions(lat, lng, when):
    """Open-Meteo model readings at (lat, lng) nearest ``when``."""
    day = when.date().isoformat()
    try:
        candidates = open_meteo.fetch_historical(f"{lat},{lng}", day, day)
    except Exception:
        return []
    out = []
    for model, rows in candidates.items():
        row = _nearest(rows, when)
        if row is None or row.get("twd_deg") is None or row.get("tws_kts") is None:
            continue
        out.append({
            "twd": row["twd_deg"], "tws": row["tws_kts"],
            "source_type": MODEL_RELIABILITY.get(model, "model_global"),
            "dt_seconds": abs((row["observed_at"] - when).total_seconds()),
        })
    return out


def build_sites(start, end, max_truth_per_station):
    """Assemble leave-one-out sites from every real station in the window."""
    repos = get_repos()
    stations = [s for s in repos.wind.list() if s.lat is not None and s.lng is not None
                and s.provider in REAL_SENSOR_PROVIDERS]

    # Preload each station's observations for the window once.
    obs_by_station = {s.id: repos.wind.list_observations(s.id, start=start, end=end, limit=500)
                      for s in stations}

    sites = []
    for held in stations:
        truth_rows = [o for o in obs_by_station[held.id] if o.twd_deg is not None][:max_truth_per_station]
        for truth in truth_rows:
            when = truth.observed_at
            contributions = []
            # Other real stations in range, their nearest observation.
            for other in stations:
                if other.id == held.id:
                    continue
                dist_km = haversine_m(held.lat, held.lng, other.lat, other.lng) / 1000.0
                if dist_km > OTHER_STATION_MAX_KM:
                    continue
                row = _nearest([o for o in obs_by_station[other.id] if o.twd_deg is not None], when)
                if row is None:
                    continue
                contributions.append({
                    "twd": row.twd_deg, "tws": row.tws_kts or 0.0, "source_type": "real_station",
                    "distance_km": dist_km, "dt_seconds": abs((row.observed_at - when).total_seconds()),
                })
            # Open-Meteo models at the held-out location/time.
            contributions.extend(_model_contributions(held.lat, held.lng, when))

            if contributions:
                sites.append({"truth_twd": truth.twd_deg, "truth_tws": truth.tws_kts,
                              "contributions": contributions})
    return sites


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="window start, YYYY-MM-DD (UTC)")
    parser.add_argument("--end", required=True, help="window end, YYYY-MM-DD (UTC)")
    parser.add_argument("--max-truth-per-station", type=int, default=20,
                        help="cap held-out truth samples per station (bounds Open-Meteo calls)")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) + timedelta(days=1)

    print(f"Assembling leave-one-out sites for {args.start}..{args.end} ...")
    sites = build_sites(start, end, args.max_truth_per_station)
    if not sites:
        print("No sites assembled (no stations/observations in window). Nothing to calibrate.")
        return

    baseline = cal.score(sites, DEFAULT_CONFIG)
    print(f"Sites: {len(sites)} | shipped-config direction MAE: {baseline['twd_mae']:.1f}° "
          f"(speed MAE: {baseline['tws_mae']})")

    candidates = cal.candidate_grid(
        prior_scales={
            "real_station": [0.6, 1.0, 1.4],
            "model_regional": [0.6, 1.0, 1.4],
            "model_global": [0.6, 1.0, 1.4],
        },
        distance_decay_km=[10.0, 15.0, 25.0],
        time_decay_seconds=[15 * 60, 30 * 60, 60 * 60],
    )
    print(f"Searching {len(candidates)} candidate configs ...")
    best, best_score = cal.calibrate(sites, candidates)

    print("\n=== suggested weighting ===")
    print(f"direction MAE: {best_score['twd_mae']:.1f}°  (baseline {baseline['twd_mae']:.1f}°) "
          f"over {best_score['n']} sites")
    print(f"distance_decay_km  = {best.distance_decay_km}")
    print(f"time_decay_seconds = {best.time_decay_seconds}")
    for source_type, weight in sorted(best.priors.items()):
        print(f"  prior[{source_type}] = {weight:.3f}")
    print("\nReview the error before applying; update SOURCE_PRIORS / decay "
          "constants in libs/xgsail_windfusion/xgsail_windfusion/__init__.py by hand.")


if __name__ == "__main__":
    main()
