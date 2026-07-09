# Position, motion, and wind estimation

A guide to how this repo turns raw sensor/API data into the numbers shown in
session analysis (legs, maneuvers, VMG, polar), and how to plug in your own
estimation algorithms without touching the rest of the pipeline.

Three concepts, kept deliberately separate throughout:

1. **Acquisition** — getting a raw reading from somewhere (a GPS fix, a
   weather station, a weather model API). No decisions, no filtering.
2. **Processing** — turning acquired data into the canonical shape the rest
   of the pipeline expects. Still no "which is right" decisions.
3. **Estimation** — an algorithm that looks at (possibly several) raw
   readings and decides the value to actually use. This is the layer you
   plug into.

---

## 1. Position & motion

### Acquisition

Two independent producers, converging on the same on-disk shape
(`{t, lat, lon, speed_kn, course, fix, ...}`), written as `gps.json` /
`gps_10hz.json`:

- **GPX** (manual import) — `backend/services/gpx.py::parse_gpx()`.
- **Device CSV** (E1/S1 formats) — `workers/process_upload/handler.py::
  process_gps()`, using the shared `_e1_row_fields()`/`_s1_row_fields()`
  helpers for field extraction (format-specific corruption handling —
  bit-flip detection, lat/lon outlier filtering — stays inline in
  `process_gps`, since it's about *this* format's data quality, not about
  turning fields into a canonical shape).

Both paths register their `gps.json`/`gps_10hz.json` blobs in
`session_streams` (`sensor_type="gps"`) via the normal ingestion flow.

### Estimation — the joint position/motion estimator

**File: `workers/process_upload/processing/track.py`.**

This is the pluggable seam. It takes the raw `gps.json` records and
produces **two distinct series** — position and motion — computed
*together*, not by two independently-callable steps:

```python
TrackEstimator = Callable[[list[dict]], tuple[list[dict], list[dict]]]
# position: list[{timestamp, lat, lon, fix_quality}]
# motion:   list[{timestamp, speed_kts, heading_deg}]
```

They're kept as two outputs (not fused into one blob) because they're
conceptually different quantities you may want to inspect or refine
separately — but computed in one pass because that's how a real joint
algorithm actually works (a Kalman filter fusing GPS fixes with heading/
speed into one state estimate can't cleanly split "estimate my position"
from "estimate my velocity" into two separate steps without losing the
coupling between them).

`track.merge(position, motion) -> list[GpsPoint]` recombines the two series
back into the `GpsPoint` shape every downstream stage already consumes
unchanged (maneuvers, legs, wind, VMG, polar). It pairs by index when both
series have the same length (true for any estimator built like today's
`parse_as_is`, which walks the same records once) — this matters because
real GPS data contains duplicate timestamps, and a timestamp-keyed dict
would silently collapse them onto one shared motion value. It only falls
back to an exact-timestamp lookup if the two series have different lengths.

### Persistence

`analyzer.py::analyze_session()` returns the two series inside its result
dict; `handler.py::process_analyze_prefix()` writes them as their own blob
artifacts (`estimated_position.json`, `estimated_motion.json`) next to
`gps.json`, and registers them in `session_streams` as
`sensor_type="estimated_position"` / `"estimated_motion"` — the same
mechanism any other sensor stream uses, just sourced from analysis instead
of raw ingestion. Not a new relational table: a session can have several
thousand points, matching `gps.json`'s own volume, and nothing today needs
point-level SQL queries across sessions.

---

## 2. Wind

Wind estimation spans two processes (backend + worker, no shared Python
package between them — separate Docker images), so it's necessarily two
seams, not one. Same distinction as above: acquisition, then estimation.

### Acquisition — two very different kinds of source

- **Real, fixed-position stations** (NOAA NDBC/METAR, a club's custom
  device) — `backend/db/models/wind.py::WindStationORM`/`WindObservationORM`.
  Each station has `keeps_local_history: bool` — if `True` (every provider
  today), the periodic fetch (`deploy/wind-scheduler.sh` →
  `POST /api/system/wind/fetch`) persists its readings, because these
  providers don't reliably keep their own history past a short public
  window. A future provider with full accessible history wouldn't need
  this.
- **Open-Meteo** — an algorithmic model API with **no fixed position** (you
  query any lat/lng) and **its own accessible history** (the archive
  endpoint covers any past date). Never persisted as a "station": there's
  nothing to cache, it's queried fresh whenever needed
  (`backend/services/wind_providers/open_meteo.py`).
  `wind_model_selection.fetch_all_candidates()` queries every candidate
  regional model (`MODEL_CANDIDATES` — finest-first, e.g. `icon_d2` for
  Europe) and returns **all** that cover the point — no picking happens
  here anymore. That decision moved to the worker (see below), which is
  the only place that also has the onboard sensor and the GPS track to
  weigh against the models.

### The determined estimate — two levels

**a) Per place/time, shared across sessions — `wind_estimates` grid.**

A spatiotemporal grid (cell size `WIND_GRID_CELL_DEG`, time bucket
`WIND_TIME_BUCKET_MIN`, both in `backend/services/wind_estimates.py`, no
"official" default yet — tune them empirically). Two sessions passing
through the same cell/bucket share (and can refine) the same row. Refining
is a **deliberately bare skeleton** —
`backend/services/wind_estimate_refinement.py`:

```python
WindEstimateRefiner = Callable[[Optional[dict], dict], dict]
# (existing_row_or_None, new_observation) -> new row to write
```

The shipped `first_write_wins` strategy does the simplest possible thing
(write once, never touch again) — see §3 below for how to replace it.

**b) Per session — `session_analysis.true_wind`.**

**File: `workers/process_upload/processing/wind_estimation.py`.** This is
the main pluggable seam for wind — a strategy sees everything gathered for
the session's track and decides the `true_wind` series legs/polar/VMG
actually get computed against:

```python
WindEstimator = Callable[
    [list[GpsPoint], list[WindReading], Optional[list[ImuReading]], list[dict]],
    list[dict],
]
# raw_wind_bundle (4th arg) — one entry per track waypoint:
# {lat, lng, real_stations: [...], model_candidates: {model_name: [...]}, grid_estimates: [...]}
```

`raw_wind_bundle` comes from `backend/services/ingestion.py::write_wind_cache()`
(written as `wind_cache.json`, the same file name as before the rewrite,
different — richer — contents), which calls
`backend/services/wind_lookup.py::gather_raw_wind()` per waypoint: a real
station's cached observations if one's in range, every Open-Meteo candidate
model, and any existing `wind_estimates` rows for that cell — no selection,
just acquisition, same principle as above.

The shipped `sensor_then_cache_then_gps` strategy, in order:

1. onboard sensor (`compute_true_wind_series` in `processing/wind.py`) —
   real measurement, tagged `"source": "sensor"`;
2. the raw bundle, flattened to one representative series per waypoint
   (`_flatten_bundle` — real station if present, else the first Open-Meteo
   model with data, else a grid estimate) and interpolated onto the track
   (`true_wind_from_cached`) — tagged `"source": "cache"`;
3. a rough direction from the GPS tack pattern alone
   (`estimate_wind_from_gps`) — tagged `"source": "gps_estimate"`, no speed
   data (`tws_kts: None`).

`_flatten_bundle` is *a* choice, not the only sensible one — a smarter
strategy sees the whole unflattened bundle (every model, every station) and
can do better (weight by distance, blend models, cross-check against the
GPS track).

### Closing the loop: sensor readings refine the grid

When `true_wind` came from a real sensor (source `"sensor"`),
`wind_estimation.refinements_from(gps, true_wind)` extracts
`{lat, lng, observed_at, twd_deg, tws_kts, source: "onboard_sensor"}` tuples
and the analysis payload carries them back to the backend as
`wind_refinements`. `routers/system.py::_apply_wind_refinements()` buckets
each into a grid cell and calls `wind_estimate_refinement.refine(...)`,
persisting the result via `repos.wind.upsert_estimate()`. This is the "a
boat with its own sensor passes through a point → refine our knowledge of
that point" loop — never triggered by cache or GPS-only estimates, since
those aren't measurements.

### Persistence & display

- `session_analysis.true_wind` — this session's own determined wind series,
  written by `routers/system.py::upsert_session_analysis` from the
  worker's `wind_refinements`/`true_wind` payload.
- The session/activity map (`MapView`, via the `sessionWind` prop) prefers
  the closest-in-time point from `true_wind` over the ephemeral WindCard/
  map live snapshot (`services/wind_lookup.live_snapshot`, `GET /api/wind/
  nearest`) whenever it's available — the live snapshot is a quick,
  unpersisted "what's the wind here now" value for pages that don't have a
  full session analysis to draw from, not the rigorous per-session
  estimate.

---

## 3. Building your own algorithm

Every seam follows the same pattern: a `STRATEGIES` dict, an
`ACTIVE_STRATEGY` constant you edit directly (no env var — this is a
research/experimentation knob, not a runtime config), and an `estimate()`/
`refine()` entrypoint that looks it up. Nothing else in the pipeline needs
to change.

### Position/motion algorithm

1. Open `workers/process_upload/processing/track.py`.
2. Write a function matching `TrackEstimator`:
   `(records: list[dict]) -> tuple[list[dict], list[dict]]`. Read whatever
   fields you need from `records` (same raw dicts `parse_as_is` reads —
   `lat`/`latitude`, `speed_kts`/`speed_kn`/`speed`, etc.); return
   `(position, motion)` with the contracts above.
   - If your algorithm can't guarantee `len(position) == len(motion)` (e.g.
     it resamples one series differently from the other), `merge()` falls
     back to an exact-timestamp match — make sure your timestamps are
     genuinely comparable in that case, or improve `merge()` itself to
     interpolate instead of exact-matching.
3. Register it: `STRATEGIES["my_algorithm"] = my_algorithm_fn`.
4. Set `ACTIVE_STRATEGY = "my_algorithm"`.
5. Rebuild the worker: `docker compose up --build -d process_upload`.
6. Test against an already-ingested session (no need to re-import):
   ```python
   # inside the backend container
   from backend.services import ingestion
   ingestion.dispatch_analysis(ingestion.bucket_name(), "processed/uploads/<upload_id>/")
   ```
   or use the "Re-run analysis" action already wired in the session detail
   page's options menu. Inspect `session_legs`/`session_maneuvers`/
   `polar_points`, or read `estimated_position.json`/`estimated_motion.json`
   directly from the session's processed prefix.

### Wind algorithm (per-session)

1. Open `workers/process_upload/processing/wind_estimation.py`.
2. Write a function matching `WindEstimator`:
   `(gps, wind, imu, raw_wind_bundle) -> list[dict]`. `raw_wind_bundle` is
   the full per-waypoint bundle (`real_stations`/`model_candidates`/
   `grid_estimates`) — use as much or as little of it as you want; you
   don't have to flatten to one series per waypoint the way the default
   does. Return the standard shape: `list[{timestamp, tws_kts, twa_deg,
   twd_deg, boat_speed_kts, heading_deg, source, ...}]`.
   - Tag `"source"` meaningfully — `refinements_from()` only feeds the grid
     from rows tagged `"sensor"` (a real measurement). If your algorithm
     ever produces a genuine measurement-grade result some other way, tag
     it `"sensor"` so it can refine the grid too; anything else should use
     a different tag so it isn't mistaken for ground truth.
3. Register + set `ACTIVE_STRATEGY`, same as above.
4. Rebuild: `docker compose up --build -d process_upload`.
5. Test the same way — re-dispatch analysis on an existing session, inspect
   `session_analysis.true_wind` (`GET /api/sessions/{id}/analysis`) and the
   resulting `polar_points`/legs.

### Wind model acquisition (which Open-Meteo models to fetch)

This is *not* the main algorithmic seam anymore, but if you want to widen
or narrow which regional models get fetched (and therefore what your wind
algorithm above has to choose from), edit `MODEL_CANDIDATES` in
`backend/services/wind_providers/open_meteo.py`. `wind_model_selection.
fetch_all_candidates()` itself has nothing to tune — it just queries every
candidate and returns whichever have data.

### Grid refinement algorithm

1. Open `backend/services/wind_estimate_refinement.py`.
2. Write a function matching `WindEstimateRefiner`:
   `(existing: Optional[dict], observation: dict) -> dict`. `existing` is
   the current row for that cell/bucket (`None` if there isn't one yet, via
   `repos.wind.get_estimate()`); `observation` carries whatever the caller
   passed (today: `{twd_deg, tws_kts, gust_kts, type, session_id,
   observed_at}` from `routers/system.py::_apply_wind_refinements`). Return
   the full row to write — `{twd_deg, tws_kts, gust_kts, confidence,
   sources}` — your function decides how to combine, weight, or ignore the
   new observation.
3. Register + set `ACTIVE_STRATEGY` in the same file.
4. Rebuild: `docker compose up --build -d backend`.
5. Test: this only fires when a session's `true_wind` came from a real
   onboard sensor (see above) — run analysis on such a session, then
   inspect `SELECT * FROM wind_estimates;` for the affected cell/bucket. You
   can also call `wind_estimate_refinement.refine(existing, observation)`
   directly in a Python shell with synthetic data to iterate faster without
   a full session round-trip.

### A note on grid parameters

`WIND_GRID_CELL_DEG`/`WIND_TIME_BUCKET_MIN`
(`backend/services/wind_estimates.py`) are plain constants — change them
directly. There's no migration involved (the table just stores whatever
`grid_lat`/`grid_lng`/`time_bucket` values `grid_cell()`/`time_bucket()`
produce), but changing the cell/bucket size after the grid already has data
means old rows won't line up with newly-computed cell keys — treat it like
any other "changed the shape of a cache" situation (fine in development,
plan for a backfill/reset in anything resembling production).
