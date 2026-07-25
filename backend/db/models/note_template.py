"""Per-user free-text templates for session crew notes (``note_templates``)
— see ``backend/db/models/session.py``'s ``notes`` column. A user writes
these for themselves (name + body) and picks one from the notes-editing
modal to prefill the textarea; the note itself stays free text and fully
editable afterwards, so a template is a starting point, not an imposed
structure. Private to the owner — no sharing, no club/group/boat link."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDPKMixin


class NoteTemplateORM(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "note_templates"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
