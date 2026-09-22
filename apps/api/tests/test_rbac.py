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

PATIENT_READ = frozenset({Permission.PATIENTS_READ})
PATIENT_REGISTRATION = frozenset({Permission.PATIENTS_CREATE, Permission.PATIENTS_UPDATE})
CLINICAL_READ = frozenset({Permission.PATIENT_ALERTS_READ, Permission.ANAMNESIS_READ})
ANAMNESIS_WRITE = frozenset(
    {
        Permission.ANAMNESIS_CREATE,
        Permission.ANAMNESIS_UPDATE,
        Permission.ANAMNESIS_FINALIZE,
    }
)
DOCUMENT_ADMIN_READ = frozenset({Permission.DOCUMENTS_ADMINISTRATIVE_READ})
DOCUMENT_ADMIN_MANAGE = frozenset({Permission.DOCUMENTS_ADMINISTRATIVE_MANAGE})
DOCUMENT_CLINICAL_READ = frozenset({Permission.DOCUMENTS_CLINICAL_READ})
DOCUMENT_CLINICAL_MANAGE = frozenset({Permission.DOCUMENTS_CLINICAL_MANAGE})

EXPECTED: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: READ_PERMISSIONS
    | {
        Permission.SETTINGS_UPDATE,
        Permission.MEMBERSHIPS_READ_CONTACT,
        Permission.MEMBERSHIPS_MANAGE_ROLE,
        Permission.MEMBERSHIPS_REMOVE,
        Permission.INVITATIONS_CREATE,
    }
    | PATIENT_READ
    | PATIENT_REGISTRATION
    | {Permission.PATIENTS_ARCHIVE}
    | DOCUMENT_ADMIN_READ
    | DOCUMENT_ADMIN_MANAGE,
    Role.DENTIST: READ_PERMISSIONS
    | PATIENT_READ
    | CLINICAL_READ
    | ANAMNESIS_WRITE
    | {Permission.PATIENT_ALERTS_MANAGE}
    | DOCUMENT_ADMIN_READ
    | DOCUMENT_CLINICAL_READ
    | DOCUMENT_CLINICAL_MANAGE,
    Role.ASSISTANT: READ_PERMISSIONS
    | PATIENT_READ
    | CLINICAL_READ
    | DOCUMENT_ADMIN_READ
    | DOCUMENT_CLINICAL_READ,
    Role.RECEPTIONIST: READ_PERMISSIONS
    | PATIENT_READ
    | PATIENT_REGISTRATION
    | DOCUMENT_ADMIN_READ
    | DOCUMENT_ADMIN_MANAGE,
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


def test_clinical_permissions_stay_away_from_administrative_roles() -> None:
    clinical = {
        Permission.PATIENT_ALERTS_READ,
        Permission.PATIENT_ALERTS_MANAGE,
        Permission.ANAMNESIS_READ,
        Permission.ANAMNESIS_CREATE,
        Permission.ANAMNESIS_UPDATE,
        Permission.ANAMNESIS_FINALIZE,
        Permission.DOCUMENTS_CLINICAL_READ,
        Permission.DOCUMENTS_CLINICAL_MANAGE,
    }
    for role in (Role.ADMIN, Role.RECEPTIONIST):
        assert ROLE_PERMISSIONS[role].isdisjoint(clinical)


def test_administrative_roles_manage_only_administrative_documents() -> None:
    for role in (Role.ADMIN, Role.RECEPTIONIST):
        assert Permission.DOCUMENTS_ADMINISTRATIVE_MANAGE in ROLE_PERMISSIONS[role]
        assert Permission.DOCUMENTS_ADMINISTRATIVE_READ in ROLE_PERMISSIONS[role]


def test_dentist_manages_clinical_documents_and_reads_administrative_ones() -> None:
    dentist = ROLE_PERMISSIONS[Role.DENTIST]
    assert Permission.DOCUMENTS_CLINICAL_MANAGE in dentist
    assert Permission.DOCUMENTS_CLINICAL_READ in dentist
    assert Permission.DOCUMENTS_ADMINISTRATIVE_READ in dentist
    assert Permission.DOCUMENTS_ADMINISTRATIVE_MANAGE not in dentist


def test_assistant_reads_documents_but_manages_none() -> None:
    assistant = ROLE_PERMISSIONS[Role.ASSISTANT]
    assert Permission.DOCUMENTS_ADMINISTRATIVE_READ in assistant
    assert Permission.DOCUMENTS_CLINICAL_READ in assistant
    assert assistant.isdisjoint(DOCUMENT_ADMIN_MANAGE | DOCUMENT_CLINICAL_MANAGE)


def test_assistant_reads_but_never_writes_clinical_records() -> None:
    assistant = ROLE_PERMISSIONS[Role.ASSISTANT]
    assert Permission.ANAMNESIS_READ in assistant
    assert assistant.isdisjoint(ANAMNESIS_WRITE)
    assert assistant.isdisjoint({Permission.PATIENT_ALERTS_MANAGE})


def test_patients_archive_is_owner_or_admin_only() -> None:
    for role in (Role.DENTIST, Role.ASSISTANT, Role.RECEPTIONIST):
        assert Permission.PATIENTS_ARCHIVE not in ROLE_PERMISSIONS[role]


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
