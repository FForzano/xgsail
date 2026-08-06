"""Feed post request DTOs (``posts``, owned by a club or a group)."""

import uuid
from typing import Optional

from pydantic import BaseModel

from ..richtext import RichTextPost


class PostCreateModel(BaseModel):
    owner_type: str  # club | group
    owner_id: uuid.UUID
    body: RichTextPost
    image_ids: list[uuid.UUID] = []
    activity_id: Optional[uuid.UUID] = None
    regatta_id: Optional[uuid.UUID] = None


class PostUpdateModel(BaseModel):
    body: RichTextPost
