from __future__ import annotations

from datetime import date

from app.core.errors import InvalidInputError

MINIMUM_AGE = 18


def is_minor(birth_date: date, *, today: date) -> bool:
    """Return True when the patient is under 18 years old on ``today``."""

    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age < MINIMUM_AGE


def validate_patient_rules(
    *,
    birth_date: date,
    guardian_name: str | None,
    guardian_relationship: str | None,
    guardian_phone: str | None,
    emergency_contact_name: str | None,
    emergency_contact_relationship: str | None,
    emergency_contact_phone: str | None,
    today: date,
) -> None:
    """Enforce the invariants the database cannot express safely.

    Birth dates cannot be in the future, minors require a complete legal
    guardian, and an informed emergency contact requires name and phone.
    """

    if birth_date > today:
        raise InvalidInputError("birth date cannot be in the future")

    if is_minor(birth_date, today=today) and not (
        guardian_name and guardian_relationship and guardian_phone
    ):
        raise InvalidInputError("minors require a guardian with name, relationship and phone")

    emergency_informed = any(
        value is not None
        for value in (
            emergency_contact_name,
            emergency_contact_relationship,
            emergency_contact_phone,
        )
    )
    if emergency_informed and not (emergency_contact_name and emergency_contact_phone):
        raise InvalidInputError("an informed emergency contact requires name and phone")
