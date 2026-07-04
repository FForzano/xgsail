"""RBAC admin request DTOs (user_roles grants)."""

import uuid
from typing import Optional

from pydantic import BaseModel


class UserRoleGrantModel(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID
    scope_club_id: Optional[uuid.UUID] = None  # NULL = global grant (superadmin only)
