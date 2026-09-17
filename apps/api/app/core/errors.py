from __future__ import annotations

from sqlalchemy.exc import IntegrityError

FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"


class DomainError(Exception):
    """Base class for application-level failures."""


class NotFoundError(DomainError):
    """The requested resource does not exist in the current scope."""


class ConflictError(DomainError):
    """The operation conflicts with existing state."""


class PermissionDeniedError(DomainError):
    """The current role does not grant the requested permission."""


class InvalidInputError(DomainError):
    """The request is well-formed but carries a value the domain rejects."""


class ContextMismatchError(DomainError):
    """The provided context diverges from the transaction context."""


def translate_integrity_error(error: IntegrityError) -> DomainError:
    """Map database integrity failures to tenant-safe domain errors.

    Foreign key violations become NotFoundError so a cross-tenant reference
    never reveals whether the referenced row exists; unique violations become
    ConflictError. Anything else stays generic.
    """

    sqlstate = getattr(error.orig, "sqlstate", None)
    if sqlstate == FOREIGN_KEY_VIOLATION:
        return NotFoundError("referenced resource was not found")
    if sqlstate == UNIQUE_VIOLATION:
        return ConflictError("resource already exists")
    return DomainError("database integrity error")
