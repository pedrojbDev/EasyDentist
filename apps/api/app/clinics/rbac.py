from __future__ import annotations

from enum import StrEnum

from app.core.errors import PermissionDeniedError


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    DENTIST = "DENTIST"
    ASSISTANT = "ASSISTANT"
    RECEPTIONIST = "RECEPTIONIST"


class Permission(StrEnum):
    CLINIC_READ = "clinic:read"
    CLINIC_UPDATE_LEGAL_NAME = "clinic:update-legal-name"
    SETTINGS_READ = "settings:read"
    SETTINGS_UPDATE = "settings:update"
    MEMBERSHIPS_READ = "memberships:read"
    MEMBERSHIPS_READ_CONTACT = "memberships:read-contact"
    MEMBERSHIPS_MANAGE_ROLE = "memberships:manage-role"
    MEMBERSHIPS_REMOVE = "memberships:remove"
    INVITATIONS_CREATE = "invitations:create"


_READ_PERMISSIONS = frozenset(
    {Permission.CLINIC_READ, Permission.SETTINGS_READ, Permission.MEMBERSHIPS_READ}
)

_MANAGEMENT_PERMISSIONS = frozenset(
    {
        Permission.SETTINGS_UPDATE,
        Permission.MEMBERSHIPS_READ_CONTACT,
        Permission.MEMBERSHIPS_MANAGE_ROLE,
        Permission.MEMBERSHIPS_REMOVE,
        Permission.INVITATIONS_CREATE,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: _READ_PERMISSIONS | _MANAGEMENT_PERMISSIONS,
    Role.DENTIST: _READ_PERMISSIONS,
    Role.ASSISTANT: _READ_PERMISSIONS,
    Role.RECEPTIONIST: _READ_PERMISSIONS,
}


def role_allows(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def require_permission(role: Role, permission: Permission) -> None:
    if not role_allows(role, permission):
        raise PermissionDeniedError(f"role {role} lacks {permission}")
