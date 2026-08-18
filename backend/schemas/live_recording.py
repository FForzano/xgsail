"""Live-recording (presence) request DTOs."""

import uuid
from typing import Optional

from pydantic import BaseModel


class LiveRecordingUpsertModel(BaseModel):
    """Announce a recording, or keep an announced one alive — one call for
    both, so the app has a single code path and no start/heartbeat race.

    ``client_recording_id`` is the phone's own recording id
    (``RecordingMeta.id``); it is what tells a heartbeat for the recording
    already announced from a brand-new one."""

    boat_id: uuid.UUID
    activity_id: Optional[uuid.UUID] = None
    client_recording_id: Optional[str] = None
