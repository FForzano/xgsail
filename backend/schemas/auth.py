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
    # Both are mandatory at registration (enforced in the router). Terms and
    # Privacy are distinct acceptances of distinct documents.
    terms_and_conditions: bool = False
    privacy_policy: bool = False


class AcceptLegalModel(BaseModel):
    """Re-acceptance of updated legal documents by a logged-in user. Each flag
    accepts the *current* version of that document (the server stamps it)."""

    terms_and_conditions: bool = False
    privacy_policy: bool = False


class SupportPromptModel(BaseModel):
    """Dismissal of the "Buy Me a Coffee" reminder banner. ``donated=True``
    when the user confirms they've supported the project (pushes the next
    reminder out much further than a plain dismissal)."""

    donated: bool = False


class LoginModel(BaseModel):
    email: str
    password: str


class ChangePasswordModel(BaseModel):
    current_password: str
    new_password: str


class RefreshModel(BaseModel):
    """Body for /auth/refresh and /auth/logout when the caller has no
    cookie jar to rely on (native clients) — the refresh token travels in
    the body instead. Web clients omit this; the cookie takes precedence
    when both are present."""

    refresh_token: Optional[str] = None
