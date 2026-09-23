from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.appointments.schemas import AgendaProfessionalCreateRequest


def test_agenda_professional_binding_requires_a_complete_cro_registration() -> None:
    """A linked agenda resource remains clinic-local and validates its own CRO."""

    member_id = uuid.uuid4()
    payload = AgendaProfessionalCreateRequest(
        name="  Dra. Ana  ",
        membership_id=member_id,
        cro_number=" 12345 ",
        cro_state="ba",
    )

    assert payload.name == "Dra. Ana"
    assert payload.membership_id == member_id
    assert payload.cro_number == "12345"
    assert payload.cro_state == "BA"

    with pytest.raises(ValidationError):
        AgendaProfessionalCreateRequest(name="Dra. Ana", cro_number="12345")
