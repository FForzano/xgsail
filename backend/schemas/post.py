"""Feed post request DTOs (``posts``, owned by a club or a group)."""

import uuid
from typing import Optional

from pydantic import BaseModel


class PostCreateModel(BaseModel):
    owner_type: str  # club | group
    owner_id: uuid.UUID
    body: str
    image_id: Optional[uuid.UUID] = None
