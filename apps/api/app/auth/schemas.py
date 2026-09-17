from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.auth.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class UserResponse(BaseModel):
    id: UUID
    email: str
    email_verified_at: datetime | None
    status: str


class LoginResponse(BaseModel):
    user: UserResponse


class CsrfTokenResponse(BaseModel):
    csrf_token: str


class SessionResponse(BaseModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool


class EmailVerificationConfirmRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class PasswordForgotRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    password: str | None = Field(
        default=None, min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH
    )
