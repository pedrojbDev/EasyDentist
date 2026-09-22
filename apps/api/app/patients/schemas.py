from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.patients.cpf import normalize_and_validate_cpf

NAME_MAX_LENGTH = 200
TEXT_MAX_LENGTH = 200
NOTES_MAX_LENGTH = 2000
PHONE_MAX_LENGTH = 40
EMAIL_MAX_LENGTH = 320


class PatientStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class PatientAlertKind(StrEnum):
    ALLERGY = "ALLERGY"
    MEDICATION = "MEDICATION"
    CLINICAL_RISK = "CLINICAL_RISK"
    OTHER = "OTHER"


class PatientAlertStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_required(value: str) -> str:
    return value.strip()


class PatientListParams(BaseModel):
    search: str | None = Field(default=None, max_length=120)
    status: PatientStatus = PatientStatus.ACTIVE
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("search")
    @classmethod
    def clean_search(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class PatientAlertListParams(BaseModel):
    status: PatientAlertStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PatientFields(BaseModel):
    full_name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    social_name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    birth_date: date | None = None
    cpf: str | None = None
    phone: str | None = Field(default=None, max_length=PHONE_MAX_LENGTH)
    phone_secondary: str | None = Field(default=None, max_length=PHONE_MAX_LENGTH)
    email: str | None = Field(default=None, max_length=EMAIL_MAX_LENGTH)
    postal_code: str | None = Field(default=None, max_length=20)
    street: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    number: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    complement: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    district: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    city: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    state: str | None = None
    occupation: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    nationality: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    birthplace: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    emergency_contact_name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    emergency_contact_relationship: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    emergency_contact_phone: str | None = Field(default=None, max_length=PHONE_MAX_LENGTH)
    guardian_name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    guardian_relationship: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    guardian_phone: str | None = Field(default=None, max_length=PHONE_MAX_LENGTH)
    administrative_notes: str | None = Field(default=None, max_length=NOTES_MAX_LENGTH)

    @field_validator(
        "social_name",
        "phone_secondary",
        "email",
        "postal_code",
        "street",
        "number",
        "complement",
        "district",
        "city",
        "occupation",
        "nationality",
        "birthplace",
        "emergency_contact_name",
        "emergency_contact_relationship",
        "emergency_contact_phone",
        "guardian_name",
        "guardian_relationship",
        "guardian_phone",
        "administrative_notes",
    )
    @classmethod
    def clean_optional_fields(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @field_validator("cpf")
    @classmethod
    def clean_cpf(cls, value: str | None) -> str | None:
        return normalize_and_validate_cpf(value)

    @field_validator("state")
    @classmethod
    def clean_state(cls, value: str | None) -> str | None:
        cleaned = _clean_optional(value)
        if cleaned is None:
            return None
        cleaned = cleaned.upper()
        if len(cleaned) != 2 or not cleaned.isalpha():
            raise ValueError("state must be a two-letter UF")
        return cleaned


class PatientCreateRequest(PatientFields):
    full_name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    birth_date: date
    phone: str = Field(min_length=1, max_length=PHONE_MAX_LENGTH)

    @field_validator("full_name", "phone")
    @classmethod
    def clean_required_fields(cls, value: str) -> str:
        cleaned = _clean_required(value)
        if not cleaned:
            raise ValueError("value cannot be blank")
        return cleaned


class PatientUpdateRequest(PatientFields):
    pass


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    full_name: str
    social_name: str | None
    birth_date: date
    cpf: str | None
    phone: str
    phone_secondary: str | None
    email: str | None
    postal_code: str | None
    street: str | None
    number: str | None
    complement: str | None
    district: str | None
    city: str | None
    state: str | None
    occupation: str | None
    nationality: str | None
    birthplace: str | None
    emergency_contact_name: str | None
    emergency_contact_relationship: str | None
    emergency_contact_phone: str | None
    guardian_name: str | None
    guardian_relationship: str | None
    guardian_phone: str | None
    administrative_notes: str | None
    status: PatientStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PatientListResponse(BaseModel):
    items: list[PatientResponse]
    total: int
    limit: int
    offset: int


class PatientAlertCreateRequest(BaseModel):
    kind: PatientAlertKind
    description: str = Field(min_length=1, max_length=500)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        cleaned = _clean_required(value)
        if not cleaned:
            raise ValueError("description cannot be blank")
        return cleaned


class PatientAlertUpdateRequest(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=500)
    status: PatientAlertStatus | None = None

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _clean_required(value)
        if not cleaned:
            raise ValueError("description cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> PatientAlertUpdateRequest:
        for field in ("description", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class PatientAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    patient_id: UUID
    kind: PatientAlertKind
    description: str
    status: PatientAlertStatus
    resolved_at: datetime | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class PatientAlertListResponse(BaseModel):
    items: list[PatientAlertResponse]
    total: int
    limit: int
    offset: int
