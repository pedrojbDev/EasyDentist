from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from app.core.context import TenantContext, UserContext


def test_user_context_is_frozen_and_slotted() -> None:
    context = UserContext(user_id=uuid4())

    with pytest.raises(FrozenInstanceError):
        context.user_id = uuid4()  # type: ignore[misc]

    assert not hasattr(context, "__dict__")


def test_tenant_context_is_frozen_and_slotted() -> None:
    context = TenantContext(user_id=uuid4(), clinic_id=uuid4())

    with pytest.raises(FrozenInstanceError):
        context.clinic_id = uuid4()  # type: ignore[misc]

    assert not hasattr(context, "__dict__")


def test_contexts_compare_by_value() -> None:
    user_id = uuid4()
    clinic_id = uuid4()

    assert UserContext(user_id=user_id) == UserContext(user_id=user_id)
    assert UserContext(user_id=user_id) != UserContext(user_id=uuid4())
    assert TenantContext(user_id=user_id, clinic_id=clinic_id) == TenantContext(
        user_id=user_id, clinic_id=clinic_id
    )
    assert TenantContext(user_id=user_id, clinic_id=clinic_id) != TenantContext(
        user_id=user_id, clinic_id=uuid4()
    )
