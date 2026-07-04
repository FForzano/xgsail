"""SQL media repository: ``images`` + ``files`` blob pointers.

No standalone permission level — access is always mediated by the parent
resource (docs/api-project.md, "Media"). Rows are soft-deleted; readers filter
``status != deleted``.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from ...db.models import FileORM, ImageORM


class SqlMediaRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    # --- images ---

    def create_image(self, *, created_by: Optional[uuid.UUID], ref: str = "") -> ImageORM:
        with self.Session() as s:
            orm = ImageORM(created_by=created_by, ref=ref, status="uploaded")
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_image(new_id)

    def get_image(self, image_id: uuid.UUID) -> Optional[ImageORM]:
        with self.Session() as s:
            return s.get(ImageORM, image_id)

    def update_image(self, image_id: uuid.UUID, changes: dict) -> Optional[ImageORM]:
        allowed = ("ref", "status")
        with self.Session() as s:
            orm = s.get(ImageORM, image_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in allowed:
                    setattr(orm, k, v)
            s.commit()
        return self.get_image(image_id)

    def soft_delete_image(self, image_id: uuid.UUID, deleted_by: Optional[uuid.UUID]) -> bool:
        with self.Session() as s:
            orm = s.get(ImageORM, image_id)
            if orm is None:
                return False
            orm.status = "deleted"
            orm.deleted_at = datetime.now(timezone.utc)
            orm.deleted_by = deleted_by
            s.commit()
            return True

    # --- files ---

    def create_file(self, *, created_by: Optional[uuid.UUID], ref: str = "") -> FileORM:
        with self.Session() as s:
            orm = FileORM(created_by=created_by, ref=ref, status="uploaded")
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_file(new_id)

    def get_file(self, file_id: uuid.UUID) -> Optional[FileORM]:
        with self.Session() as s:
            return s.get(FileORM, file_id)

    def update_file(self, file_id: uuid.UUID, changes: dict) -> Optional[FileORM]:
        allowed = ("ref", "status")
        with self.Session() as s:
            orm = s.get(FileORM, file_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in allowed:
                    setattr(orm, k, v)
            s.commit()
        return self.get_file(file_id)

    def soft_delete_file(self, file_id: uuid.UUID, deleted_by: Optional[uuid.UUID]) -> bool:
        with self.Session() as s:
            orm = s.get(FileORM, file_id)
            if orm is None:
                return False
            orm.status = "deleted"
            orm.deleted_at = datetime.now(timezone.utc)
            orm.deleted_by = deleted_by
            s.commit()
            return True
