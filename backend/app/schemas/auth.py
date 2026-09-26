"""Auth API schemas — strict request validation, hash-free responses."""

from __future__ import annotations

from datetime import datetime

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, Field, field_validator


def _normalize_email(value: str) -> str:
    """Normalize + validate. Error text stays generic (no reflection)."""
    try:
        info = validate_email(value, check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError("Enter a valid email address.") from exc
    return info.normalized


class RegisterRequest(BaseModel):
    email: str = Field(max_length=255)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=128)

    _normalize_email = field_validator("email")(_normalize_email)

    @field_validator("display_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be empty.")
        return v


class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=1, max_length=128)

    _normalize_email = field_validator("email")(_normalize_email)


class UserPublic(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class AuthResponse(BaseModel):
    """Login/register response: the user, never any session id or hash."""

    user: UserPublic


class MeResponse(UserPublic):
    pass


class LogoutResponse(BaseModel):
    logged_out: bool
