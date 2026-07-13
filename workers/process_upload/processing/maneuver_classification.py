"""Pluggable maneuver classifiers — Stage 2 of the two-stage detection
pipeline. Stage 1 (``maneuvers._detect_candidates``) produces
``ManeuverCandidate``s with a ``features`` dict; a classifier here maps each
candidate to a ``ManeuverType`` — or to ``None`` meaning "false alarm, not a
real maneuver", so Stage 2 can *reject* a candidate, not only label it.

Add a classifier by writing a function with the ``ManeuverClassifier``
signature and registering it below; swap ``ACTIVE_CLASSIFIER`` to experiment
(constant, not env-configurable — change it and rebuild the worker image, same
idiom as ``wind_estimation.ACTIVE_STRATEGY``).

Two classifiers are described here:

- ``geometric`` (default): today's rule — tack if the average absolute angle
  to the wind axis is < 90° (bow crosses the wind), else gybe. Never returns
  ``None`` or ``COURSE_CHANGE``, so detection behavior is unchanged.
- ``_ml_classifier`` (FUTURE, NOT registered): a trained XGBoost/NN model that
  maps ``candidate.features`` to {tack, gybe, course_change} or ``None`` (false
  alarm). Left as a stub so the seam is visible without pulling in ML deps.
"""

import os
from typing import Callable, Optional

from .models import ManeuverCandidate, ManeuverType

ManeuverClassifier = Callable[[ManeuverCandidate], "Optional[ManeuverType]"]


def geometric_classifier(cand: ManeuverCandidate) -> "Optional[ManeuverType]":
    """Tack = the bow crosses head-to-wind (both headings within 90° of the
    wind axis); gybe = the stern crosses (both beyond 90°). Reads the
    classifier inputs from the candidate's feature dict. Returns TACK or GYBE
    only — never ``None`` (no false-alarm rejection) and never ``COURSE_CHANGE``
    — so the current behavior is preserved exactly."""
    rel_before = cand.features["rel_before"]
    rel_after = cand.features["rel_after"]
    avg_abs_rel = (abs(rel_before) + abs(rel_after)) / 2
    return ManeuverType.TACK if avg_abs_rel < 90 else ManeuverType.GYBE


CLASSIFIERS: "dict[str, ManeuverClassifier]" = {
    "geometric": geometric_classifier,
}

# Change this (and rebuild the worker image) to switch classifiers.
ACTIVE_CLASSIFIER = "geometric"


def classify_maneuver(cand: ManeuverCandidate) -> "Optional[ManeuverType]":
    """Dispatch to the active classifier. ``None`` = false alarm → the caller
    (``detect_maneuvers``) drops the candidate."""
    return CLASSIFIERS[ACTIVE_CLASSIFIER](cand)


# --------------------------------------------------------------------------- #
# FUTURE: ML classifier seam — deliberately NOT registered / not active.
# --------------------------------------------------------------------------- #

# Env var pointing at the trained model artifact (local path or object-store
# URI). The classifier *selection* is a compile-time constant (ACTIVE_CLASSIFIER);
# only the trained weights are provided at runtime via this env var. Do NOT wire
# ACTIVE_CLASSIFIER itself to an env var — that would break the wind-module idiom.
MANEUVER_MODEL_PATH_ENV = "MANEUVER_MODEL_PATH"


def _load_maneuver_model():
    """FUTURE: lazily load + cache the Step-2 model artifact from
    ``os.environ[MANEUVER_MODEL_PATH_ENV]``. Import sklearn/xgboost/torch INSIDE
    this function so the deps are only required once the ML path is active.
    Not called until ``_ml_classifier`` is registered."""
    path = os.environ.get(MANEUVER_MODEL_PATH_ENV)
    raise NotImplementedError(
        f"Maneuver model loading not implemented yet (would load from {path!r})."
    )


def _ml_classifier(cand: ManeuverCandidate) -> "Optional[ManeuverType]":
    """FUTURE Step 2 — NOT registered / not active. Intended shape once it
    lands:

      1. lazily load a model artifact (``_load_maneuver_model``), cached
         module-level;
      2. build the feature vector from ``cand.features`` in the order given by
         ``maneuver_features.ENABLED_FEATURES`` / ``FEATURE_SCHEMA_VERSION`` —
         the exact training-time order;
      3. predict a label and map it to {TACK, GYBE, COURSE_CHANGE};
      4. below a confidence threshold, return ``None`` (false alarm) or fall
         back to ``geometric_classifier``.

    Registering this also requires the ``course_change`` enum member (already
    present) + the DB CHECK migration (already applied) + adding the ML deps to
    ``requirements.txt``.
    """
    raise NotImplementedError("ML maneuver classifier not implemented yet")
