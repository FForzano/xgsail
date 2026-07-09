"""Spatiotemporal grid quantization for ``wind_estimates`` — the single
place that turns a (lat, lng, time) into the cell/bucket key the determined-
wind table is keyed on. Kept as runtime constants, not baked into the
schema, since you'll want to tune them while experimenting with refinement
algorithms (see ``services/wind_estimate_refinement.py``).
"""

from datetime import datetime, timezone

# Cell size in degrees — no "official" default yet, tune empirically.
# ~0.03 deg is roughly 3km of latitude at mid-latitudes; longitude cells
# shrink with cos(latitude), so this is an approximation, not a fixed-area
# grid — fine for a first cut.
WIND_GRID_CELL_DEG = 0.03

# Time bucket width, minutes.
WIND_TIME_BUCKET_MIN = 15


def grid_cell(lat: float, lng: float) -> "tuple[float, float]":
    """Quantize a coordinate to its cell center."""
    return (
        round(lat / WIND_GRID_CELL_DEG) * WIND_GRID_CELL_DEG,
        round(lng / WIND_GRID_CELL_DEG) * WIND_GRID_CELL_DEG,
    )


def time_bucket(at: datetime) -> datetime:
    """Truncate a timestamp to its bucket start, UTC."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    at = at.astimezone(timezone.utc)
    bucket_seconds = WIND_TIME_BUCKET_MIN * 60
    epoch = at.timestamp()
    truncated = epoch - (epoch % bucket_seconds)
    return datetime.fromtimestamp(truncated, tz=timezone.utc)
