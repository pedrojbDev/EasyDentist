from __future__ import annotations

import argon2
import pytest
from argon2 import PasswordHasher as Argon2PasswordHasher

from app.auth.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, PasswordHasher
from app.auth.settings import AuthSettings

PASSWORD = "correct horse battery staple"


@pytest.fixture
def hasher() -> PasswordHasher:
    return PasswordHasher(AuthSettings.from_environment({}))


def test_hash_uses_argon2id_v19_with_planned_parameters(hasher: PasswordHasher) -> None:
    digest = hasher.hash(PASSWORD)
    parameters = argon2.extract_parameters(digest)

    assert parameters.type == argon2.Type.ID
    assert parameters.version == 19
    assert parameters.time_cost == 3
    assert parameters.memory_cost == 65536
    assert parameters.parallelism == 1
    assert parameters.salt_len == 16
    assert parameters.hash_len == 32


def test_hash_rejects_password_below_minimum(hasher: PasswordHasher) -> None:
    with pytest.raises(ValueError, match="between 12 and 128"):
        hasher.hash("a" * (MIN_PASSWORD_LENGTH - 1))


def test_hash_rejects_password_above_maximum(hasher: PasswordHasher) -> None:
    with pytest.raises(ValueError, match="between 12 and 128"):
        hasher.hash("a" * (MAX_PASSWORD_LENGTH + 1))


def test_verify_and_rehash_accepts_current_hash(hasher: PasswordHasher) -> None:
    digest = hasher.hash(PASSWORD)

    verified, new_hash = hasher.verify_and_rehash(PASSWORD, digest)

    assert verified is True
    assert new_hash is None


def test_verify_and_rehash_rejects_wrong_password(hasher: PasswordHasher) -> None:
    digest = hasher.hash(PASSWORD)

    verified, new_hash = hasher.verify_and_rehash("wrong password entirely", digest)

    assert verified is False
    assert new_hash is None


def test_verify_and_rehash_rejects_malformed_hash(hasher: PasswordHasher) -> None:
    verified, new_hash = hasher.verify_and_rehash(PASSWORD, "not-an-argon2-hash")

    assert verified is False
    assert new_hash is None


def test_verify_and_rehash_upgrades_outdated_parameters(hasher: PasswordHasher) -> None:
    outdated = Argon2PasswordHasher(
        time_cost=2, memory_cost=8192, parallelism=2, hash_len=32, salt_len=16
    ).hash(PASSWORD)

    verified, new_hash = hasher.verify_and_rehash(PASSWORD, outdated)

    assert verified is True
    assert new_hash is not None
    parameters = argon2.extract_parameters(new_hash)
    assert parameters.time_cost == 3
    assert parameters.memory_cost == 65536
    assert parameters.parallelism == 1
