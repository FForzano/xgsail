"""Cross-session leaderboard endpoint (``/api/leaderboard``).

Ranks precomputed leaderboard entries by a chosen metric, optionally filtered
by boat class.
"""

from fastapi import APIRouter, HTTPException, Query

from ._common import DATA_PREFIX, load_json_or_404

router = APIRouter(prefix="/api", tags=["leaderboard"])


@router.get("/leaderboard")
def get_leaderboard(
    metric: str = Query("max_speed", description="Ranking metric"),
    boat_class: str | None = None,
    limit: int = 20,
):
    """Get leaderboard rankings across sessions."""
    key = f"{DATA_PREFIX}/leaderboard.json"
    try:
        data = load_json_or_404(key)
    except HTTPException:
        return {"entries": [], "metric": metric}

    entries = data.get("entries", [])

    if boat_class:
        entries = [e for e in entries if e.get("boat_class") == boat_class]

    # Sort by metric
    entries.sort(key=lambda e: e.get(metric, 0), reverse=True)

    return {"entries": entries[:limit], "metric": metric}
