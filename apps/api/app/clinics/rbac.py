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
    PATIENTS_READ = "patients:read"
    PATIENTS_CREATE = "patients:create"
    PATIENTS_UPDATE = "patients:update"
    PATIENTS_ARCHIVE = "patients:archive"
    PATIENT_ALERTS_READ = "patient-alerts:read"
    PATIENT_ALERTS_MANAGE = "patient-alerts:manage"


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

_PATIENT_READ = frozenset({Permission.PATIENTS_READ})
_PATIENT_REGISTRATION = frozenset({Permission.PATIENTS_CREATE, Permission.PATIENTS_UPDATE})
_PATIENT_ARCHIVE = frozenset({Permission.PATIENTS_ARCHIVE})
_CLINICAL_ALERTS = frozenset({Permission.PATIENT_ALERTS_READ, Permission.PATIENT_ALERTS_MANAGE})

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: _READ_PERMISSIONS
    | _MANAGEMENT_PERMISSIONS
    | _PATIENT_READ
    | _PATIENT_REGISTRATION
    | _PATIENT_ARCHIVE,
    Role.DENTIST: _READ_PERMISSIONS | _PATIENT_READ | _CLINICAL_ALERTS,
    Role.ASSISTANT: _READ_PERMISSIONS | _PATIENT_READ | frozenset({Permission.PATIENT_ALERTS_READ}),
    Role.RECEPTIONIST: _READ_PERMISSIONS | _PATIENT_READ | _PATIENT_REGISTRATION,
}


def role_allows(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def require_permission(role: Role, permission: Permission) -> None:
    if not role_allows(role, permission):
        raise PermissionDeniedError(f"role {role} lacks {permission}")
