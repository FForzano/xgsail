"""Sensor time-series endpoint (``/api/data/{device_id}/{date}``).

Loads each requested sensor's JSON from the blob store and merges the records
by timestamp into the shape the frontend timeline expects.
"""

from fastapi import APIRouter, HTTPException, Query

from ._common import DATA_PREFIX, load_json_or_404

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/{device_id}/{date}")
def get_sensor_data(
    device_id: str,
    date: str,
    sensors: str = Query("gps,imu,wind,pressure", description="Comma-separated sensor list"),
    start: float | None = None,
    end: float | None = None,
    resolution: int = Query(1, description="Downsample factor"),
):
    """Get sensor time-series data for a session, merged by timestamp.

    Returns data in merged format expected by frontend:
    {
        data: [{t, gps: {...}, imu: {...}, pressure: {...}, wind: {...}}, ...],
        start_time: "...",
        end_time: "..."
    }
    """
    # Load each sensor's data
    sensor_data = {}
    for sensor in sensors.split(","):
        sensor = sensor.strip()
        # PPK data is stored as ppk_gps.json, not ppk.json
        if sensor == "ppk":
            key = f"{DATA_PREFIX}/{device_id}/{date}/ppk_gps.json"
        else:
            key = f"{DATA_PREFIX}/{device_id}/{date}/{sensor}.json"
        try:
            data = load_json_or_404(key)
            records = data if isinstance(data, list) else data.get("data", [])
            sensor_data[sensor] = records
        except HTTPException:
            sensor_data[sensor] = []

    # Merge by timestamp - collect all unique timestamps
    merged = {}  # timestamp -> {t, gps: {...}, imu: {...}, ...}

    for sensor, records in sensor_data.items():
        for record in records:
            t = record.get("t")
            if not t:
                continue
            if t not in merged:
                merged[t] = {"t": t}
            # Nest sensor data under sensor key (exclude 't' from nested object)
            sensor_record = {k: v for k, v in record.items() if k != "t"}
            merged[t][sensor] = sensor_record

    # Sort by timestamp and convert to list
    data = [merged[t] for t in sorted(merged.keys())]

    # Time filtering using ISO string comparison (works for chronological order)
    # Note: start/end params are currently unused as frontend filters via timeController
    # TODO: Support ISO string time bounds if needed

    # Downsample
    if resolution > 1:
        data = data[::resolution]

    # Calculate time bounds
    start_time = data[0]["t"] if data else None
    end_time = data[-1]["t"] if data else None

    return {
        "data": data,
        "start_time": start_time,
        "end_time": end_time,
    }
