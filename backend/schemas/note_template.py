"""Note-template request DTOs (per-user session-notes snippets)."""

from typing import Optional

from pydantic import BaseModel


class NoteTemplateCreateModel(BaseModel):
    name: str
    body: str


class NoteTemplateUpdateModel(BaseModel):
    name: Optional[str] = None
    body: Optional[str] = None
