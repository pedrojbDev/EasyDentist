from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

NAME_MAX_LENGTH = 200
CRO_NUMBER_MAX_LENGTH = 30


def _clean_required(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("value cannot be blank")
    return cleaned


class ProfessionalProfileRequest(BaseModel):
    """Professional name, CRO number and UF as informed by the user.

    The API does not validate the CRO against an external registry; the value
    is stored and snapshotted exactly as declared here.
    """

    model_config = ConfigDict(extra="forbid")

    professional_name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    cro_number: str = Field(min_length=1, max_length=CRO_NUMBER_MAX_LENGTH)
    cro_state: str

    @field_validator("professional_name", "cro_number")
    @classmethod
    def clean_required_fields(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("cro_state")
    @classmethod
    def clean_state(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) != 2 or not cleaned.isalpha():
            raise ValueError("cro_state must be a two-letter UF")
        return cleaned


class ProfessionalProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    professional_name: str
    cro_number: str
    cro_state: str
    created_at: datetime
    updated_at: datetime
