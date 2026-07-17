"""Feed posts (``posts``) — owned by either a club or a group.

Generic instead of duplicated per owner type: clubs and groups already share
the same shape (members, join/invite, visibility — see ``club.py``/
``group.py``), so a single polymorphic table (``owner_type``/``owner_id``)
serves both feeds and leaves room for a future personal aggregated feed
across a user's clubs/groups without another migration. ``owner_id`` has no
FK (it points at either ``clubs`` or ``groups`` depending on ``owner_type``)
— validated in the router, not the DB. Create/delete only: no edit, so no
``updated_at``.
"""

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, CreatedAtMixin, UUIDPKMixin, enum_check

POST_OWNER_TYPES = ("club", "group")


class PostORM(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "posts"
    __table_args__ = (enum_check("owner_type", POST_OWNER_TYPES),)

    owner_type: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    image_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
