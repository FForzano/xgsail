"""User profile request DTOs."""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class UserUpdateModel(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[date] = None
    password: Optional[str] = None  # change-password path (router re-hashes)
