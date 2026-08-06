"""Note-template request DTOs (per-user session-notes snippets)."""

from typing import Optional

from pydantic import BaseModel

from ..richtext import RichTextFull


class NoteTemplateCreateModel(BaseModel):
    name: str
    body: RichTextFull


class NoteTemplateUpdateModel(BaseModel):
    name: Optional[str] = None
    body: RichTextFull = None
