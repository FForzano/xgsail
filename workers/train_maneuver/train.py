#!/usr/bin/env python3
"""Manual training entrypoint for the Stage 2 maneuver classifier
(workers/process_upload/processing/maneuver_classification.py's future
``_ml_classifier``).

NOT triggered automatically by anything — no storage event, no docker-compose
`up` dependency, no cron. You run it by hand when you have a training CSV
ready (see scripts/export_maneuver_training_data.py for how to build one):

    python -m workers.train_maneuver.train --data maneuvers.csv --output model/

or, self-hosted, without a local Python env:

    docker compose --profile training run --rm train_maneuver \\
        python train.py --data /data/maneuvers.csv --output /data/model/

Trains an XGBoost multi-class classifier over the feature columns from
maneuver_features.py, using a session-grouped train/val/test split (see
dataset.py) so no session's maneuvers leak across the split. Writes:

  - model.json       — the trained XGBoost booster (native format)
  - metadata.json     — feature column order, classes, schema version, and
                         eval metrics; the future _ml_classifier needs this
                         to know the exact column order/label mapping used
                         at training time
"""

import argparse
import json
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_sample_weight

from .dataset import FEATURE_COLUMNS, load_dataset, review_stats, split
from workers.process_upload.processing.maneuver_features import FEATURE_SCHEMA_VERSION


def train(args: argparse.Namespace) -> None:
    df = load_dataset(args.data)

    stats = review_stats(df)
    print(
        f"labels: {stats['corrected']}/{stats['total']} human-corrected, "
        f"{stats['algorithm_only']}/{stats['total']} still the algorithm's raw guess "
        "(label == label_original)"
    )
    if stats["corrected"] == 0:
        print(
            "WARNING: no row has been human-corrected yet — every label is the "
            "geometric classifier's own output, so the model can at best learn "
            "to imitate it, not improve on it (no false_alarm/course_change "
            "examples either). See workers/train_maneuver/README.md.",
        )

    data = split(df, val_size=args.val_size, test_size=args.test_size, random_state=args.seed)

    print(
        f"train={len(data.train.X)} val={len(data.val.X)} test={len(data.test.X)} "
        f"rows, classes={data.classes}"
    )

    class_to_idx = {c: i for i, c in enumerate(data.classes)}
    y_train = data.train.y.map(class_to_idx)
    y_val = data.val.y.map(class_to_idx)
    y_test = data.test.y.map(class_to_idx)

    # XGBoost's missing-value handling (NaN routed to the split-optimal
    # branch at train time) means the None-valued features documented in
    # maneuver_features.py (no wind axis, no IMU, short windows) don't need
    # imputation — pandas read_csv already turns empty cells into NaN.
    sample_weight = compute_sample_weight("balanced", y_train)

    model = xgb.XGBClassifier(
        objective="multi:softprob",
        num_class=len(data.classes),
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        early_stopping_rounds=args.early_stopping_rounds,
        eval_metric="mlogloss",
        random_state=args.seed,
    )
    model.fit(
        data.train.X,
        y_train,
        sample_weight=sample_weight,
        eval_set=[(data.val.X, y_val)],
        verbose=args.verbose,
    )

    y_pred = model.predict(data.test.X)
    report = classification_report(
        y_test, y_pred, target_names=data.classes, output_dict=True, zero_division=0
    )
    print(classification_report(y_test, y_pred, target_names=data.classes, zero_division=0))
    print("Confusion matrix (rows=true, cols=predicted):")
    print(data.classes)
    print(confusion_matrix(y_test, y_pred))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(str(output_dir / "model.json"))

    metadata = {
        "feature_columns": FEATURE_COLUMNS,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "classes": data.classes,
        "hyperparameters": {
            "n_estimators": args.n_estimators,
            "max_depth": args.max_depth,
            "learning_rate": args.learning_rate,
            "best_iteration": int(model.best_iteration)
            if getattr(model, "best_iteration", None) is not None
            else None,
        },
        "row_counts": {
            "train": len(data.train.X),
            "val": len(data.val.X),
            "test": len(data.test.X),
        },
        "test_classification_report": report,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Saved model + metadata to {output_dir}/")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, help="Training CSV (see scripts/export_maneuver_training_data.py)")
    parser.add_argument("--output", required=True, help="Output directory for model.json + metadata.json")
    parser.add_argument("--val-size", type=float, default=0.15)
    parser.add_argument("--test-size", type=float, default=0.15)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--early-stopping-rounds", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    train(args)


if __name__ == "__main__":
    main()
