"""Auth request DTOs.

``email`` is a plain ``str`` (not pydantic ``EmailStr``) to avoid pulling in the
``email-validator`` dependency; the router does a light format check.
"""

from typing import Optional

from pydantic import BaseModel


class RegisterModel(BaseModel):
    email: str
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    terms_and_conditions: bool = False


class LoginModel(BaseModel):
    email: str
    password: str


class ChangePasswordModel(BaseModel):
    current_password: str
    new_password: str
