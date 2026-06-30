"""Boat catalog endpoints (``/api/boats*``).

Read-only listing + single fetch of boat profiles via the repository layer.
"""

from fastapi import APIRouter, HTTPException

from ._common import repos

router = APIRouter(prefix="/api/boats", tags=["boats"])


@router.get("")
def list_boats():
    """List all boat profiles."""
    return {"boats": [b.to_dict() for b in repos.boats.list()]}


@router.get("/{boat_id}")
def get_boat(boat_id: str):
    """Get a specific boat profile."""
    boat = repos.boats.get(boat_id)
    if boat is None:
        raise HTTPException(404, f"Boat not found: {boat_id}")
    return boat.to_dict()
