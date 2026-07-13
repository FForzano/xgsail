"""Shared circular-angle helpers.

Extracted from ``maneuvers.py`` so both the detector and the feature
extractor (``maneuver_features.py``) can reuse them without a circular
import. Behavior is identical to the previous private implementations.
"""

import numpy as np


def angular_diff(a: "float | np.ndarray", b: "float | np.ndarray") -> "float | np.ndarray":
    """Signed angular difference a - b, result in [-180, 180]."""
    d = a - b
    if isinstance(d, np.ndarray):
        d = (d + 180) % 360 - 180
    else:
        d = (d + 180) % 360 - 180
    return d


def circular_mean(angles_deg: np.ndarray) -> float:
    """Mean of a set of angles via their unit vectors — a plain arithmetic
    mean breaks near the 0°/360° wraparound."""
    rad = np.radians(angles_deg)
    return float(np.degrees(np.arctan2(np.mean(np.sin(rad)), np.mean(np.cos(rad)))) % 360)
