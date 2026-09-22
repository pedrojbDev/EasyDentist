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
    ANAMNESIS_READ = "anamnesis:read"
    ANAMNESIS_CREATE = "anamnesis:create"
    ANAMNESIS_UPDATE = "anamnesis:update"
    ANAMNESIS_FINALIZE = "anamnesis:finalize"
    DOCUMENTS_ADMINISTRATIVE_READ = "documents-administrative:read"
    DOCUMENTS_ADMINISTRATIVE_MANAGE = "documents-administrative:manage"
    DOCUMENTS_CLINICAL_READ = "documents-clinical:read"
    DOCUMENTS_CLINICAL_MANAGE = "documents-clinical:manage"
    AGENDA_CATALOG_READ = "agenda:catalog-read"
    AGENDA_RESOURCES_MANAGE = "agenda:resources-manage"
    AGENDA_READ = "agenda:read"
    AGENDA_APPOINTMENTS_MANAGE = "agenda:appointments-manage"


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
_ANAMNESIS_READ = frozenset({Permission.ANAMNESIS_READ})
_ANAMNESIS_WRITE = frozenset(
    {
        Permission.ANAMNESIS_CREATE,
        Permission.ANAMNESIS_UPDATE,
        Permission.ANAMNESIS_FINALIZE,
    }
)
_DOCUMENT_ADMIN = frozenset(
    {
        Permission.DOCUMENTS_ADMINISTRATIVE_READ,
        Permission.DOCUMENTS_ADMINISTRATIVE_MANAGE,
    }
)
_DOCUMENT_ADMIN_READ = frozenset({Permission.DOCUMENTS_ADMINISTRATIVE_READ})
_DOCUMENT_CLINICAL = frozenset(
    {
        Permission.DOCUMENTS_CLINICAL_READ,
        Permission.DOCUMENTS_CLINICAL_MANAGE,
    }
)
_DOCUMENT_CLINICAL_READ = frozenset({Permission.DOCUMENTS_CLINICAL_READ})
_AGENDA_READ = frozenset({Permission.AGENDA_CATALOG_READ, Permission.AGENDA_READ})
_AGENDA_RESOURCE_MANAGEMENT = frozenset({Permission.AGENDA_RESOURCES_MANAGE})
_AGENDA_APPOINTMENT_MANAGEMENT = frozenset({Permission.AGENDA_APPOINTMENTS_MANAGE})

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: (
        _READ_PERMISSIONS
        | _MANAGEMENT_PERMISSIONS
        | _PATIENT_READ
        | _PATIENT_REGISTRATION
        | _PATIENT_ARCHIVE
        | _DOCUMENT_ADMIN
        | _AGENDA_READ
        | _AGENDA_RESOURCE_MANAGEMENT
        | _AGENDA_APPOINTMENT_MANAGEMENT
    ),
    Role.DENTIST: (
        _READ_PERMISSIONS
        | _PATIENT_READ
        | _CLINICAL_ALERTS
        | _ANAMNESIS_READ
        | _ANAMNESIS_WRITE
        | _DOCUMENT_ADMIN_READ
        | _DOCUMENT_CLINICAL
        | _AGENDA_READ
        | _AGENDA_APPOINTMENT_MANAGEMENT
    ),
    Role.ASSISTANT: (
        _READ_PERMISSIONS
        | _PATIENT_READ
        | frozenset({Permission.PATIENT_ALERTS_READ})
        | _ANAMNESIS_READ
        | _DOCUMENT_ADMIN_READ
        | _DOCUMENT_CLINICAL_READ
        | _AGENDA_READ
    ),
    Role.RECEPTIONIST: (
        _READ_PERMISSIONS
        | _PATIENT_READ
        | _PATIENT_REGISTRATION
        | _DOCUMENT_ADMIN
        | _AGENDA_READ
        | _AGENDA_APPOINTMENT_MANAGEMENT
    ),
}


def role_allows(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def require_permission(role: Role, permission: Permission) -> None:
    if not role_allows(role, permission):
        raise PermissionDeniedError(f"role {role} lacks {permission}")
