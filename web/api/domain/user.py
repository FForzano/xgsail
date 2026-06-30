"""User domain model. RBAC (roles/permissions/scopes) is layered on top in the
auth layer; this is the identity record itself."""

from typing import Optional

from .base import DomainModel


class User(DomainModel):
    id: Optional[int] = None
    email: str
    name: Optional[str] = None
    is_active: bool = True
    is_superadmin: bool = False
    created_at: Optional[str] = None
