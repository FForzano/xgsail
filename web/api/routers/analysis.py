"""Per-session analysis endpoints (``/api/analysis/*``).

Serves the precomputed ``analysis.json`` for a session, plus narrow views over
it (maneuvers, legs, polar, stats). The sub-views call ``get_analysis`` in this
same module, so they stay co-located.
"""

from fastapi import APIRouter

from ._common import DATA_PREFIX, load_json_or_404

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/{device_id}/{date}")
def get_analysis(device_id: str, date: str):
    """Get full analysis results for a session."""
    key = f"{DATA_PREFIX}/{device_id}/{date}/analysis.json"
    return load_json_or_404(key)


@router.get("/{device_id}/{date}/maneuvers")
def get_maneuvers(device_id: str, date: str):
    """Get maneuver detection results."""
    analysis = get_analysis(device_id, date)
    return {
        "maneuvers": analysis.get("maneuvers", []),
        "summary": analysis.get("maneuver_summary", {}),
    }


@router.get("/{device_id}/{date}/legs")
def get_legs(device_id: str, date: str):
    """Get straight-line leg analysis."""
    analysis = get_analysis(device_id, date)
    return {
        "legs": analysis.get("legs", []),
        "comparison": analysis.get("leg_comparison", {}),
    }


@router.get("/{device_id}/{date}/polar")
def get_polar(device_id: str, date: str):
    """Get polar diagram data."""
    analysis = get_analysis(device_id, date)
    return {"polar": analysis.get("polar", {})}


@router.get("/{device_id}/{date}/stats")
def get_stats(device_id: str, date: str):
    """Get statistical analysis (violin, correlations)."""
    analysis = get_analysis(device_id, date)
    return {
        "violin": analysis.get("violin", {}),
        "correlations": analysis.get("correlations", {}),
        "session_stats": analysis.get("session_stats", {}),
        "leg_ranking": analysis.get("leg_ranking", []),
    }
