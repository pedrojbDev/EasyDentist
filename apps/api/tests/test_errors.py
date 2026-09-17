from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    translate_integrity_error,
)


class FakeDatabaseError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("database error")
        self.sqlstate = sqlstate


def integrity_error(sqlstate: str) -> IntegrityError:
    return IntegrityError("INSERT INTO app.example", {}, FakeDatabaseError(sqlstate))


def test_foreign_key_violation_becomes_not_found() -> None:
    error = translate_integrity_error(integrity_error("23503"))

    assert isinstance(error, NotFoundError)
    assert isinstance(error, DomainError)


def test_unique_violation_becomes_conflict() -> None:
    error = translate_integrity_error(integrity_error("23505"))

    assert isinstance(error, ConflictError)
    assert isinstance(error, DomainError)


def test_other_integrity_errors_stay_generic() -> None:
    error = translate_integrity_error(integrity_error("23502"))

    assert type(error) is DomainError


def test_error_without_sqlstate_stays_generic() -> None:
    error = translate_integrity_error(
        IntegrityError("INSERT INTO app.example", {}, ValueError("boom"))
    )

    assert type(error) is DomainError
