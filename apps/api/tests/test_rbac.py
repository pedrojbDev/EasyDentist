from __future__ import annotations

from typing import cast

import pytest

from app.clinics.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    require_permission,
    role_allows,
)
from app.core.errors import PermissionDeniedError

READ_PERMISSIONS = frozenset(
    {Permission.CLINIC_READ, Permission.SETTINGS_READ, Permission.MEMBERSHIPS_READ}
)

EXPECTED: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: READ_PERMISSIONS
    | {
        Permission.SETTINGS_UPDATE,
        Permission.MEMBERSHIPS_READ_CONTACT,
        Permission.MEMBERSHIPS_MANAGE_ROLE,
        Permission.MEMBERSHIPS_REMOVE,
        Permission.INVITATIONS_CREATE,
    },
    Role.DENTIST: READ_PERMISSIONS,
    Role.ASSISTANT: READ_PERMISSIONS,
    Role.RECEPTIONIST: READ_PERMISSIONS,
}


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("permission", list(Permission))
def test_role_permission_matrix(role: Role, permission: Permission) -> None:
    assert role_allows(role, permission) is (permission in EXPECTED[role])


def test_owner_holds_every_declared_permission() -> None:
    assert ROLE_PERMISSIONS[Role.OWNER] == frozenset(Permission)


def test_every_declared_permission_is_granted_to_some_role() -> None:
    declared = set().union(*ROLE_PERMISSIONS.values())
    assert declared == set(Permission)


def test_management_permissions_are_owner_or_admin_only() -> None:
    management = {
        Permission.CLINIC_UPDATE_LEGAL_NAME,
        Permission.SETTINGS_UPDATE,
        Permission.MEMBERSHIPS_READ_CONTACT,
        Permission.MEMBERSHIPS_MANAGE_ROLE,
        Permission.MEMBERSHIPS_REMOVE,
        Permission.INVITATIONS_CREATE,
    }
    for role in (Role.DENTIST, Role.ASSISTANT, Role.RECEPTIONIST):
        assert ROLE_PERMISSIONS[role].isdisjoint(management)


def test_undeclared_permission_is_denied_for_every_role() -> None:
    undeclared = cast(Permission, "clinic:delete")
    for role in Role:
        assert role_allows(role, undeclared) is False


def test_unknown_role_is_denied() -> None:
    unknown = cast(Role, "AUDITOR")
    assert role_allows(unknown, Permission.CLINIC_READ) is False


def test_require_permission_raises_for_denied_role() -> None:
    with pytest.raises(PermissionDeniedError):
        require_permission(Role.DENTIST, Permission.SETTINGS_UPDATE)
    with pytest.raises(PermissionDeniedError):
        require_permission(Role.ADMIN, Permission.CLINIC_UPDATE_LEGAL_NAME)


def test_require_permission_allows_granted_permission() -> None:
    require_permission(Role.ADMIN, Permission.SETTINGS_UPDATE)
    require_permission(Role.OWNER, Permission.CLINIC_UPDATE_LEGAL_NAME)
