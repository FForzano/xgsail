"""NOAA buoy data endpoints (``/api/buoys*``).

Thin HTTP layer over ``noaa_buoys`` for listing Boston Harbor stations and
fetching/interpolating their time-series data.
"""

from fastapi import APIRouter, HTTPException, Query

from ..noaa_buoys import (
    BOSTON_BUOYS,
    get_all_buoys_data,
    get_buoy_snapshot,
    fetch_buoy_data_for_timerange,
)

router = APIRouter(prefix="/api/buoys", tags=["buoys"])


@router.get("")
def list_buoys():
    """List all Boston Harbor area buoys with their metadata."""
    buoys = []
    for station_id, meta in BOSTON_BUOYS.items():
        buoys.append({
            "station_id": station_id,
            "name": meta["name"],
            "lat": meta["lat"],
            "lon": meta["lon"],
            "type": meta["type"],
            "data_types": meta["data"],
            "color": meta["color"],
        })
    return {"buoys": buoys}


@router.get("/data")
def get_buoys_data(
    start_ts: float = Query(..., description="Start timestamp (Unix)"),
    end_ts: float = Query(..., description="End timestamp (Unix)"),
):
    """
    Get NOAA buoy data for all Boston Harbor buoys within a time range.
    Returns metadata and time-series data for each buoy.
    """
    data = get_all_buoys_data(start_ts, end_ts)

    # Format response
    result = {}
    for station_id, buoy in data.items():
        result[station_id] = {
            "station_id": station_id,
            "name": buoy["name"],
            "lat": buoy["lat"],
            "lon": buoy["lon"],
            "color": buoy["color"],
            "type": buoy["type"],
            "has_data": buoy["has_data"],
            "data_points": buoy["data_points"],
        }

    return {"buoys": result}


@router.get("/snapshot")
def get_buoys_snapshot(
    timestamp: float = Query(..., description="Target timestamp (Unix)"),
    start_ts: float = Query(None, description="Session start (for caching)"),
    end_ts: float = Query(None, description="Session end (for caching)"),
):
    """
    Get interpolated buoy values at a specific timestamp.
    Useful for real-time display during timeline scrubbing.
    """
    # Use provided range or default to +/- 4 hours
    if start_ts is None:
        start_ts = timestamp - 4 * 3600
    if end_ts is None:
        end_ts = timestamp + 4 * 3600

    buoys_data = get_all_buoys_data(start_ts, end_ts)
    snapshot = get_buoy_snapshot(buoys_data, timestamp)

    return {"timestamp": timestamp, "buoys": snapshot}


@router.get("/{station_id}/data")
def get_single_buoy_data(
    station_id: str,
    start_ts: float = Query(..., description="Start timestamp (Unix)"),
    end_ts: float = Query(..., description="End timestamp (Unix)"),
):
    """Get data for a specific buoy within a time range."""
    if station_id not in BOSTON_BUOYS:
        raise HTTPException(404, f"Unknown buoy: {station_id}")

    meta = BOSTON_BUOYS[station_id]
    data_points = fetch_buoy_data_for_timerange(station_id, start_ts, end_ts)

    return {
        "station_id": station_id,
        "name": meta["name"],
        "lat": meta["lat"],
        "lon": meta["lon"],
        "color": meta["color"],
        "data_points": data_points,
    }
