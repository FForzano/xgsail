# train_maneuver

Manual, on-demand training for the Stage 2 ML maneuver classifier — the
`_ml_classifier` seam described in
[`maneuver_classification.py`](../process_upload/processing/maneuver_classification.py).
Today the active classifier is `geometric_classifier` (rule-based); this
worker is how you train a replacement once you have enough labeled data.

Nothing here runs automatically: no storage trigger, no `docker compose up`
dependency, no cron. You run it by hand, when you have a training CSV ready.

## 1. Export a training CSV

```bash
# inside the backend container / any environment with the DB reachable
python scripts/export_maneuver_training_data.py --out train-data/maneuvers.csv
```

This queries every `session_maneuvers` row that has a persisted `features`
JSON blob and flattens it into a CSV: one row per detected maneuver, one
column per feature in
[`maneuver_features.py`](../process_upload/processing/maneuver_features.py),
plus `session_id`, `maneuver_id`, `schema_version`, and five
label/provenance columns: `label`, `label_original`, `corrected_by_user`,
`source`, `rejected`.

### Correcting / rejecting / adding a maneuver (in-app)

Three ways a user can override the algorithm, all in
[`backend/routers/sessions.py`](../../backend/routers/sessions.py), same
edit permission as the session itself (boat owner/admin or the activity's
creator):

- `PATCH .../maneuvers/{id}` `{"maneuver_type": "tack"|"gybe"|"course_change"}`
  (`correct_maneuver`) — overrides a detected maneuver's type.
  `original_maneuver_type` stays frozen at the pipeline's first guess;
  `corrected_by_user` flips to `true`.
- `PATCH .../maneuvers/{id}/reject` `{"rejected": true|false}`
  (`reject_maneuver`) — marks a detected maneuver as not real at all (or
  undoes that). Only valid for `source == "detected"` rows.
- `POST .../maneuvers` `{"maneuver_type", "start_time", "end_time"}`
  (`add_maneuver`) — adds a maneuver the algorithm missed. Inserts a
  `pending` row immediately, then a worker round-trip
  (`workers/process_upload/processing/maneuvers.py::compute_manual_maneuver`)
  fills in real stats/features, same math a detected maneuver gets.
- `DELETE .../maneuvers/{id}` (`delete_maneuver`) — removes a
  `source == "manual"` row outright (safe: no algorithm-origin counterpart
  could reappear and duplicate it).

**All three survive a reanalysis, and reanalysis never duplicates them.**
`POST .../reanalyze` no longer blindly replaces every `session_maneuvers`
row — `repos.sessions.upsert_maneuvers` (via
`backend/services/maneuver_reconciliation.py`) only replaces rows nobody
has touched (`source == "detected"`, not corrected, not rejected); any
manually-added, corrected, or rejected row is left alone, and a fresh
algorithm candidate whose time window turns out to describe the same event
is dropped instead of inserted next to it.

### The label columns

- `label` = the row's current `maneuver_type` — **except** a rejected row
  (`rejected == true`) always exports as `label = "false_alarm"` regardless
  of `maneuver_type`, the real negative-example signal
  [`maneuver_classification.py`](../process_upload/processing/maneuver_classification.py)'s
  false-alarm return contract was always designed for. Otherwise this is
  ground truth for any corrected row, and the algorithm's raw guess
  otherwise.
- `label_original` = `original_maneuver_type`, frozen at the algorithm's
  first guess (or the manual type given at creation, for `source ==
  "manual"` rows — there was never an algorithm guess to diverge from).
  `label != label_original` ⇒ a human touched this row in the app.
- `corrected_by_user`, `source`, `rejected` = the DB's own columns, kept
  alongside for filtering without recomputing anything.

You can still hand-edit `label` further in a spreadsheet before training —
just don't touch `label_original`/`corrected_by_user`/`source`/`rejected`,
they're read straight from the DB. The `label` classes the trainer uses are
whatever's actually present in the column — no hardcoded list.

`train.py` prints the corrected-vs-algorithm-only count before every
training run — if it says 0 corrected, every label is still the geometric
classifier's own output, so the model can at best learn to imitate it, not
improve on it.

Rows whose `schema_version` doesn't match the current
`FEATURE_SCHEMA_VERSION` are still exported, flagged with a warning at
training time — decide whether their feature columns still mean the same
thing before including them.

## 2. Train

Locally (repo root, with `workers/train_maneuver/requirements.txt`
installed):

```bash
python -m workers.train_maneuver.train \
    --data train-data/maneuvers.csv \
    --output train-data/model
```

Or self-hosted, without touching your local Python env — the `training`
compose profile keeps this out of `docker compose up`, so it must be named
explicitly:

```bash
docker compose --profile training run --rm train_maneuver \
    python -m workers.train_maneuver.train \
    --data /data/maneuvers.csv --output /data/model
```

(`./train-data/` on the host is mounted at `/data` in the container — put
the exported CSV there first.)

Useful flags (all optional, see `--help` for the full list):

| Flag | Default | Meaning |
|---|---|---|
| `--val-size` / `--test-size` | 0.15 / 0.15 | Fraction of *sessions* (not rows) held out for validation/test — see below |
| `--n-estimators` | 300 | Max boosting rounds (early stopping usually cuts this short) |
| `--max-depth` | 4 | Tree depth — keep shallow, this is a small tabular dataset |
| `--learning-rate` | 0.05 | XGBoost `eta` |
| `--early-stopping-rounds` | 20 | Stop once val `mlogloss` stops improving for this many rounds |

The split is **grouped by `session_id`**: every maneuver from the same
session lands entirely in train, val, or test. Maneuvers from one session
share wind conditions, crew, and boat, so a row-level split would leak
information across the split and overstate accuracy.

Class imbalance (tacks vastly outnumber gybes/course_change/false_alarm) is
handled via `sample_weight="balanced"` rather than resampling — no synthetic
rows, and it keeps every maneuver traceable back to a real session.

XGBoost handles the `None`/`NaN` feature values natively (routes them to the
best branch at split time) — no imputation needed for maneuvers with no wind
axis or no IMU.

## 3. Output

```
train-data/model/
├── model.json      # trained XGBoost booster, native format
└── metadata.json   # feature column order, classes, schema version,
                     # hyperparameters, and the held-out test set's
                     # classification report
```

`metadata.json`'s `feature_columns` is the exact order `_ml_classifier` must
build its feature vector in — it's read from
`maneuver_features.FEATURE_COLUMNS`, the same list the export script used,
so training and inference can never drift apart silently.

Training also prints a classification report and confusion matrix for the
test set to stdout — check per-class F1 (especially `course_change` and
`false_alarm`, the minority classes that matter most for not over-detecting)
before trusting the model, not just overall accuracy.

## 4. Wiring it up (not done by this worker)

This worker only produces `model.json` + `metadata.json` on disk — it does
not deploy them. To make the trained model active:

1. Upload `model.json` + `metadata.json` to object storage (or leave them
   local for self-hosted).
2. Implement `_load_maneuver_model()` and register `_ml_classifier` in
   [`maneuver_classification.py`](../process_upload/processing/maneuver_classification.py)
   — it already documents the intended shape (load model via
   `MANEUVER_MODEL_PATH_ENV`, build the feature vector in
   `metadata.json`'s `feature_columns` order, predict, apply a confidence
   threshold before trusting a label over a `None`/false-alarm fallback).
3. Flip `ACTIVE_CLASSIFIER = "ml"` and rebuild the `process_upload` worker
   image (classifier selection is a compile-time constant, same idiom as
   `wind_estimation.ACTIVE_STRATEGY` — not env-configurable).
