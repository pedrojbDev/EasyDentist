from __future__ import annotations

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.auth.settings import AuthSettings

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class PasswordHasher:
    def __init__(self, settings: AuthSettings) -> None:
        self._hasher = Argon2PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_kib,
            parallelism=settings.argon2_parallelism,
            hash_len=32,
            salt_len=16,
        )

    def hash(self, password: str) -> str:
        self._validate_length(password)
        return self._hasher.hash(password)

    def verify_and_rehash(self, password: str, password_hash: str) -> tuple[bool, str | None]:
        try:
            self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False, None
        if self._hasher.check_needs_rehash(password_hash):
            return True, self.hash(password)
        return True, None

    @staticmethod
    def _validate_length(password: str) -> None:
        if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            raise ValueError(
                f"password must be between {MIN_PASSWORD_LENGTH} and "
                f"{MAX_PASSWORD_LENGTH} characters"
            )
