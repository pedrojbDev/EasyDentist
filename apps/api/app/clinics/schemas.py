from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from uuid import UUID
from zoneinfo import available_timezones

from pydantic import BaseModel, Field, field_validator

from app.clinics.rbac import Role


@lru_cache(maxsize=1)
def known_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


class ClinicResponse(BaseModel):
    id: UUID
    slug: str
    legal_name: str
    status: str
    role: Role


class ClinicUpdateRequest(BaseModel):
    legal_name: str = Field(min_length=1, max_length=200)


class ClinicSettingsResponse(BaseModel):
    clinic_id: UUID
    display_name: str
    timezone: str
    locale: str
    currency: str


class ClinicSettingsUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = None
    locale: str | None = Field(default=None, min_length=2, max_length=10)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in known_timezones():
            raise ValueError("timezone must be a valid IANA timezone")
        return value


class MembershipResponse(BaseModel):
    id: UUID
    user_id: UUID
    role: Role
    status: str
    created_at: datetime
    email: str | None = None


class MembershipRoleUpdateRequest(BaseModel):
    role: Role


class MembershipInvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Role


class MembershipInvitationResponse(BaseModel):
    membership_id: UUID
    invitation_expires_at: datetime
