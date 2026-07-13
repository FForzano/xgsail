"""Load a maneuver training CSV (produced by
``scripts/export_maneuver_training_data.py``, or hand-built in the same
shape) and split it into train/val/test.

The split is GROUPED BY ``session_id``: maneuvers from the same session share
wind conditions, crew, and boat, so splitting by row would leak information
between train and test and overstate accuracy. Grouping keeps every maneuver
of a given session on the same side of the split.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

# Kept in sync with maneuver_features.CORE_FEATURES / ENABLED_FEATURES by the
# export script, which writes exactly these columns (plus the meta columns
# below) — imported here too so a mismatch fails loudly instead of silently
# training on the wrong columns.
from workers.process_upload.processing.maneuver_features import (
    CORE_FEATURES,
    ENABLED_FEATURES,
    FEATURE_SCHEMA_VERSION,
)

FEATURE_COLUMNS = list(dict.fromkeys(CORE_FEATURES + tuple(ENABLED_FEATURES)))
META_COLUMNS = ["maneuver_id", "session_id", "label", "label_original",
               "corrected_by_user", "source", "rejected", "schema_version"]

# `label` classes are inferred from whatever's present in the CSV (see
# `split` below) rather than hardcoded. Besides "tack"/"gybe"/"course_change"
# (backend/db/models/session.py MANEUVER_TYPES, the only values the in-app
# correction endpoint accepts), the export script emits "false_alarm" for any
# row the user rejected in the app (PATCH .../maneuvers/{id}/reject) — the
# real negative-example signal maneuver_classification.py's false-alarm
# return contract was always designed for.


@dataclass
class Dataset:
    X: pd.DataFrame
    y: pd.Series
    groups: pd.Series


@dataclass
class Split:
    train: Dataset
    val: Dataset
    test: Dataset
    classes: "list[str]"


def load_dataset(csv_path: str, *, warn_schema_mismatch: bool = True) -> pd.DataFrame:
    """Read the CSV and sanity-check it before splitting."""
    df = pd.read_csv(csv_path)

    missing = [c for c in META_COLUMNS + FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"{csv_path} is missing expected column(s): {missing}. "
            "Was it produced by scripts/export_maneuver_training_data.py "
            "against the current maneuver_features schema?"
        )

    df = df.dropna(subset=["label", "session_id"])
    df = df.fillna({"label_original": df["label"]})

    if warn_schema_mismatch:
        mismatched = df[df["schema_version"] != FEATURE_SCHEMA_VERSION]
        if len(mismatched):
            print(
                f"WARNING: {len(mismatched)}/{len(df)} rows have "
                f"schema_version != {FEATURE_SCHEMA_VERSION} (current). "
                "Their feature columns may mean something different than "
                "today's extractors — review before training on them.",
            )

    return df


def review_stats(df: pd.DataFrame) -> dict:
    """How many rows carry a human-corrected label vs. the algorithm's raw
    guess — see the export script's docstring for why ``label_original`` is
    the only provenance signal available (no in-app review flow yet)."""
    corrected = int((df["label"] != df["label_original"]).sum())
    return {"total": len(df), "corrected": corrected, "algorithm_only": len(df) - corrected}


def split(
    df: pd.DataFrame,
    *,
    val_size: float = 0.15,
    test_size: float = 0.15,
    random_state: int = 42,
) -> Split:
    """Group-aware train/val/test split by ``session_id``."""
    classes = sorted(df["label"].unique())

    groups = df["session_id"]
    gss_test = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_val_idx, test_idx = next(gss_test.split(df, groups=groups))
    train_val_df, test_df = df.iloc[train_val_idx], df.iloc[test_idx]

    relative_val_size = val_size / (1 - test_size)
    gss_val = GroupShuffleSplit(n_splits=1, test_size=relative_val_size, random_state=random_state)
    train_idx, val_idx = next(gss_val.split(train_val_df, groups=train_val_df["session_id"]))
    train_df, val_df = train_val_df.iloc[train_idx], train_val_df.iloc[val_idx]

    def _to_dataset(part: pd.DataFrame) -> Dataset:
        return Dataset(
            X=part[FEATURE_COLUMNS].astype(float),
            y=part["label"],
            groups=part["session_id"],
        )

    return Split(
        train=_to_dataset(train_df),
        val=_to_dataset(val_df),
        test=_to_dataset(test_df),
        classes=classes,
    )
