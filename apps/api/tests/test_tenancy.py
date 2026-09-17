from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

import pytest

from app.core.context import TenantContext, UserContext
from app.core.errors import ContextMismatchError
from app.core.tenancy import (
    SESSION_CONTEXT_KEY,
    ensure_context_matches,
    tenant_transaction,
    user_transaction,
)


class FakeSession:
    def __init__(self) -> None:
        self.info: dict[str, object] = {}
        self.executed: list[tuple[str, Mapping[str, str] | None]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def execute(self, statement: object, parameters: Mapping[str, str] | None = None) -> None:
        self.executed.append((str(statement), parameters))

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


@pytest.mark.anyio
async def test_user_transaction_sets_user_guc_with_bind_parameter() -> None:
    session = FakeSession()
    context = UserContext(user_id=uuid4())

    async with user_transaction(FakeSessionFactory(session), context):  # type: ignore[arg-type]
        pass

    assert len(session.executed) == 1
    statement, parameters = session.executed[0]
    assert "set_config('app.current_user_id', :user_id, true)" in statement
    assert parameters == {"user_id": str(context.user_id)}
    assert session.committed is True
    assert session.closed is True


@pytest.mark.anyio
async def test_tenant_transaction_sets_both_gucs_with_bind_parameters() -> None:
    session = FakeSession()
    context = TenantContext(user_id=uuid4(), clinic_id=uuid4())

    async with tenant_transaction(FakeSessionFactory(session), context):  # type: ignore[arg-type]
        pass

    assert len(session.executed) == 1
    statement, parameters = session.executed[0]
    assert "set_config('app.current_user_id', :user_id, true)" in statement
    assert "set_config('app.current_clinic_id', :clinic_id, true)" in statement
    assert parameters == {"user_id": str(context.user_id), "clinic_id": str(context.clinic_id)}
    assert session.committed is True
    assert session.closed is True


@pytest.mark.anyio
async def test_tenant_transaction_rolls_back_and_closes_on_error() -> None:
    session = FakeSession()
    context = TenantContext(user_id=uuid4(), clinic_id=uuid4())

    with pytest.raises(ValueError, match="boom"):
        async with tenant_transaction(FakeSessionFactory(session), context):  # type: ignore[arg-type]
            raise ValueError("boom")

    assert session.committed is False
    assert session.rolled_back is True
    assert session.closed is True


class FakeInfoSession:
    def __init__(self) -> None:
        self.info: dict[str, object] = {}


def test_ensure_context_matches_requires_a_stored_context() -> None:
    session = FakeInfoSession()

    with pytest.raises(ContextMismatchError):
        ensure_context_matches(session, UserContext(user_id=uuid4()))  # type: ignore[arg-type]


def test_ensure_context_matches_rejects_another_user() -> None:
    session = FakeInfoSession()
    session.info[SESSION_CONTEXT_KEY] = UserContext(user_id=uuid4())

    with pytest.raises(ContextMismatchError):
        ensure_context_matches(session, UserContext(user_id=uuid4()))  # type: ignore[arg-type]


def test_ensure_context_matches_allows_user_scope_for_the_same_user() -> None:
    user_id = uuid4()
    clinic_id = uuid4()
    session = FakeInfoSession()
    session.info[SESSION_CONTEXT_KEY] = TenantContext(user_id=user_id, clinic_id=clinic_id)

    ensure_context_matches(session, UserContext(user_id=user_id))  # type: ignore[arg-type]
    ensure_context_matches(session, TenantContext(user_id=user_id, clinic_id=clinic_id))  # type: ignore[arg-type]


def test_ensure_context_matches_rejects_another_clinic() -> None:
    user_id = uuid4()
    session = FakeInfoSession()
    session.info[SESSION_CONTEXT_KEY] = TenantContext(user_id=user_id, clinic_id=uuid4())

    with pytest.raises(ContextMismatchError):
        ensure_context_matches(session, TenantContext(user_id=user_id, clinic_id=uuid4()))  # type: ignore[arg-type]


def test_ensure_context_matches_rejects_tenant_call_inside_user_transaction() -> None:
    user_id = uuid4()
    session = FakeInfoSession()
    session.info[SESSION_CONTEXT_KEY] = UserContext(user_id=user_id)

    with pytest.raises(ContextMismatchError):
        ensure_context_matches(session, TenantContext(user_id=user_id, clinic_id=uuid4()))  # type: ignore[arg-type]
