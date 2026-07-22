"""Third-party wearable-cloud account links (``/api/integrations``).

Scaffolding only — reserves the API surface the frontend's "in arrivo"
Garmin/Polar device-picker cards will call once a real OAuth integration
ships (see `backend/db/models/integration.py` for the inert
`integration_connections` table this will read/write, and
docs/device-protocol.md §8 for the separate BLE-relay transport XGSail's own
hardware uses instead). Every route here is a stub: no OAuth flow, no token
storage, no polling — just a 503 so the frontend can treat "not implemented
yet" as a real, typed API response instead of a 404.
"""

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_user
from ..db.models.integration import INTEGRATION_PROVIDERS

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def _require_known_provider(provider: str) -> None:
    if provider not in INTEGRATION_PROVIDERS:
        raise HTTPException(404, "Unknown provider")


@router.get("")
def list_integrations(request: Request):
    """Would list the calling user's connections; not implemented yet."""
    require_user(request)
    raise HTTPException(503, "Wearable integrations are coming soon")


@router.post("/{provider}/connect")
def connect_integration(provider: str, request: Request):
    """Would start the provider's OAuth flow; not implemented yet."""
    require_user(request)
    _require_known_provider(provider)
    raise HTTPException(503, f"{provider} integration is coming soon")


@router.delete("/{provider}")
def disconnect_integration(provider: str, request: Request):
    """Would revoke the stored connection; not implemented yet."""
    require_user(request)
    _require_known_provider(provider)
    raise HTTPException(503, f"{provider} integration is coming soon")
