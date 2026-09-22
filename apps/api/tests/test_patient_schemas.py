from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.patients.schemas import (
    PatientAlertListParams,
    PatientCreateRequest,
    PatientListParams,
    PatientUpdateRequest,
)


def test_patient_list_params_defaults() -> None:
    params = PatientListParams()

    assert params.search is None
    assert params.status == "ACTIVE"
    assert params.limit == 20
    assert params.offset == 0


def test_patient_list_params_trim_search_and_blank_is_absent() -> None:
    assert PatientListParams(search="  Ana  ").search == "Ana"
    assert PatientListParams(search="   ").search is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("limit", 0), ("limit", 101), ("offset", -1), ("search", "x" * 121)],
)
def test_patient_list_params_reject_out_of_range(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        PatientListParams(**{field: value})


def test_alert_list_params_accept_every_status_and_bound_limits() -> None:
    params = PatientAlertListParams()

    assert params.status is None
    assert params.limit == 20
    assert params.offset == 0
    assert PatientAlertListParams(status="RESOLVED").status == "RESOLVED"
    with pytest.raises(ValidationError):
        PatientAlertListParams(limit=101)


def test_create_request_normalizes_cpf_state_and_blank_strings() -> None:
    payload = PatientCreateRequest(
        full_name="  Ana Souza  ",
        birth_date=date(1990, 1, 1),
        phone=" +55 71 90000-0000 ",
        cpf="529.982.247-25",
        state="ba",
        email="   ",
        social_name="",
    )

    assert payload.full_name == "Ana Souza"
    assert payload.phone == "+55 71 90000-0000"
    assert payload.cpf == "52998224725"
    assert payload.state == "BA"
    assert payload.email is None
    assert payload.social_name is None


def test_create_request_rejects_invalid_cpf() -> None:
    with pytest.raises(ValidationError):
        PatientCreateRequest(
            full_name="Ana",
            birth_date=date(1990, 1, 1),
            phone="+5571900000000",
            cpf="529.982.247-24",
        )


def test_create_request_requires_name_birth_date_and_phone() -> None:
    with pytest.raises(ValidationError):
        PatientCreateRequest()
    with pytest.raises(ValidationError):
        PatientCreateRequest(full_name="Ana", birth_date=date(1990, 1, 1), phone="   ")


def test_update_request_tracks_explicit_null_from_unset() -> None:
    payload = PatientUpdateRequest(phone_secondary=None, email="ana@example.com")

    assert payload.model_dump(exclude_unset=True) == {
        "phone_secondary": None,
        "email": "ana@example.com",
    }
    assert PatientUpdateRequest().model_dump(exclude_unset=True) == {}


def test_update_request_validates_cpf_when_provided() -> None:
    assert PatientUpdateRequest(cpf="529.982.247-25").cpf == "52998224725"
    assert PatientUpdateRequest(cpf="  ").cpf is None
    with pytest.raises(ValidationError):
        PatientUpdateRequest(cpf="111.111.111-11")


@pytest.mark.parametrize("field", ["full_name", "birth_date", "phone"])
def test_update_request_rejects_explicit_null_on_mandatory_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        PatientUpdateRequest(**{field: None})


@pytest.mark.parametrize("payload", [{"full_name": "   "}, {"phone": ""}])
def test_update_request_rejects_blank_mandatory_fields(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        PatientUpdateRequest(**payload)


def test_update_request_accepts_valid_partial_mandatory_fields() -> None:
    payload = PatientUpdateRequest(full_name="  Ana Souza  ", phone=" +5571999112222 ")

    assert payload.full_name == "Ana Souza"
    assert payload.phone == "+5571999112222"
    assert payload.model_dump(exclude_unset=True) == {
        "full_name": "Ana Souza",
        "phone": "+5571999112222",
    }
