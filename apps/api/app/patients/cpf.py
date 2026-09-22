from __future__ import annotations

CPF_LENGTH = 11


def normalize_cpf(raw: str) -> str:
    """Return only the digits of ``raw``; formatting is discarded."""

    return "".join(character for character in raw if character.isdigit())


def is_valid_cpf(digits: str) -> bool:
    """Validate an 11-digit CPF, including both check digits.

    Repeated-digit sequences are rejected even though the checksum formula
    accepts them.
    """

    if len(digits) != CPF_LENGTH or not digits.isdigit():
        return False
    if len(set(digits)) == 1:
        return False

    numbers = [int(character) for character in digits]
    for length in (9, 10):
        total = sum(numbers[index] * (length + 1 - index) for index in range(length))
        check_digit = (total * 10) % CPF_LENGTH
        if check_digit == 10:
            check_digit = 0
        if check_digit != numbers[length]:
            return False
    return True


def normalize_and_validate_cpf(raw: str | None) -> str | None:
    """Normalize an optional CPF, returning None for blank input.

    Raises ``ValueError`` when the value is present but invalid, so Pydantic
    validators surface it as a 422 response.
    """

    if raw is None or not raw.strip():
        return None
    digits = normalize_cpf(raw)
    if not is_valid_cpf(digits):
        raise ValueError("invalid cpf")
    return digits
