from __future__ import annotations

from datetime import date

import pytest

from app.core.errors import InvalidInputError
from app.patients.rules import is_minor, validate_patient_rules

TODAY = date(2026, 9, 22)


def make_rules(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "birth_date": date(1990, 1, 1),
        "guardian_name": None,
        "guardian_relationship": None,
        "guardian_phone": None,
        "emergency_contact_name": None,
        "emergency_contact_relationship": None,
        "emergency_contact_phone": None,
    }
    values.update(overrides)
    return values


def test_is_minor_turns_adult_on_the_eighteenth_birthday() -> None:
    assert is_minor(date(2008, 9, 23), today=TODAY) is True
    assert is_minor(date(2008, 9, 22), today=TODAY) is False
    assert is_minor(date(2008, 9, 21), today=TODAY) is False


def test_future_birth_date_is_rejected() -> None:
    with pytest.raises(InvalidInputError):
        validate_patient_rules(**make_rules(birth_date=date(2026, 9, 23)), today=TODAY)


def test_birth_today_is_not_treated_as_future() -> None:
    validate_patient_rules(
        **make_rules(
            birth_date=TODAY,
            guardian_name="Maria",
            guardian_relationship="Mãe",
            guardian_phone="+5571999999999",
        ),
        today=TODAY,
    )


def test_minor_requires_complete_guardian() -> None:
    minor = date(2015, 5, 10)
    with pytest.raises(InvalidInputError):
        validate_patient_rules(**make_rules(birth_date=minor), today=TODAY)
    with pytest.raises(InvalidInputError):
        validate_patient_rules(
            **make_rules(
                birth_date=minor,
                guardian_name="Maria",
                guardian_relationship="Mãe",
            ),
            today=TODAY,
        )

    validate_patient_rules(
        **make_rules(
            birth_date=minor,
            guardian_name="Maria",
            guardian_relationship="Mãe",
            guardian_phone="+5571999999999",
        ),
        today=TODAY,
    )


def test_adult_does_not_require_guardian() -> None:
    validate_patient_rules(**make_rules(birth_date=date(1990, 1, 1)), today=TODAY)


def test_emergency_contact_requires_name_and_phone_when_informed() -> None:
    with pytest.raises(InvalidInputError):
        validate_patient_rules(
            **make_rules(emergency_contact_name="João"),
            today=TODAY,
        )
    with pytest.raises(InvalidInputError):
        validate_patient_rules(
            **make_rules(emergency_contact_relationship="Irmão"),
            today=TODAY,
        )

    validate_patient_rules(
        **make_rules(
            emergency_contact_name="João",
            emergency_contact_phone="+5571988888888",
        ),
        today=TODAY,
    )
