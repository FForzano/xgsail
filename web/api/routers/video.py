"""Per-session video stream endpoint (``/api/video/{device_id}/{date}``).

Reads camera playlist references out of the session manifest.
"""

from fastapi import APIRouter

from ._common import DATA_PREFIX, load_json_or_404

router = APIRouter(prefix="/api/video", tags=["video"])


@router.get("/{device_id}/{date}")
def get_video(device_id: str, date: str):
    """Get video stream URLs for a session."""
    key = f"{DATA_PREFIX}/{device_id}/{date}/manifest.json"
    manifest = load_json_or_404(key)

    cameras = {}
    for cam in manifest.get("cameras", []):
        cam_name = cam.get("name", "default")
        cameras[cam_name] = {
            "playlist_url": cam.get("playlist_url"),
            "start_time": cam.get("start_time"),
            "end_time": cam.get("end_time"),
            "duration_sec": cam.get("duration_sec"),
        }

    return {"cameras": cameras}
