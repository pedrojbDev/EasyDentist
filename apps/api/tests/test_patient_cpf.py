from __future__ import annotations

import pytest

from app.patients.cpf import is_valid_cpf, normalize_and_validate_cpf, normalize_cpf

VALID_CPF = "52998224725"
VALID_CPF_FORMATTED = "529.982.247-25"
OTHER_VALID_CPF = "11144477735"


def test_normalize_cpf_strips_every_non_digit() -> None:
    assert normalize_cpf(VALID_CPF_FORMATTED) == VALID_CPF
    assert normalize_cpf(" 529 982 247 25 ") == VALID_CPF
    assert normalize_cpf("") == ""
    assert normalize_cpf("nao-e-cpf") == ""


def test_is_valid_cpf_accepts_known_valid_numbers() -> None:
    assert is_valid_cpf(VALID_CPF) is True
    assert is_valid_cpf(OTHER_VALID_CPF) is True


def test_is_valid_cpf_rejects_broken_checksum_and_shape() -> None:
    assert is_valid_cpf("52998224724") is False
    assert is_valid_cpf("12345678900") is False
    assert is_valid_cpf("5299822472") is False
    assert is_valid_cpf("529982247251") is False
    assert is_valid_cpf("") is False


def test_is_valid_cpf_rejects_repeated_digits() -> None:
    for digit in "0123456789":
        assert is_valid_cpf(digit * 11) is False


def test_normalize_and_validate_cpf_returns_digits() -> None:
    assert normalize_and_validate_cpf(VALID_CPF_FORMATTED) == VALID_CPF


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_normalize_and_validate_cpf_treats_blank_as_absent(raw: str | None) -> None:
    assert normalize_and_validate_cpf(raw) is None


@pytest.mark.parametrize("raw", ["52998224724", "11111111111", "123", "abc"])
def test_normalize_and_validate_cpf_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_and_validate_cpf(raw)
