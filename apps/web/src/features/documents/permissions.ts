import type { DocumentCategory } from './api';

export type DocumentCapabilities = {
  canReadAdministrative: boolean;
  canManageAdministrative: boolean;
  canReadClinical: boolean;
  canManageClinical: boolean;
};

const DENIED: DocumentCapabilities = {
  canReadAdministrative: false,
  canManageAdministrative: false,
  canReadClinical: false,
  canManageClinical: false,
};

const CAPABILITIES: Record<string, DocumentCapabilities> = {
  OWNER: {
    canReadAdministrative: true,
    canManageAdministrative: true,
    canReadClinical: true,
    canManageClinical: true,
  },
  ADMIN: {
    canReadAdministrative: true,
    canManageAdministrative: true,
    canReadClinical: false,
    canManageClinical: false,
  },
  DENTIST: {
    canReadAdministrative: true,
    canManageAdministrative: false,
    canReadClinical: true,
    canManageClinical: true,
  },
  ASSISTANT: {
    canReadAdministrative: true,
    canManageAdministrative: false,
    canReadClinical: true,
    canManageClinical: false,
  },
  RECEPTIONIST: {
    canReadAdministrative: true,
    canManageAdministrative: true,
    canReadClinical: false,
    canManageClinical: false,
  },
};

export const DOCUMENT_CATEGORIES: DocumentCategory[] = ['ADMINISTRATIVE', 'CLINICAL'];

/** Mirrors the API RBAC matrix; anything unknown is denied. */
export function documentCapabilities(role: string): DocumentCapabilities {
  return CAPABILITIES[role] ?? DENIED;
}

export function canReadCategory(
  capabilities: DocumentCapabilities,
  category: DocumentCategory,
): boolean {
  return category === 'CLINICAL'
    ? capabilities.canReadClinical
    : capabilities.canReadAdministrative;
}

export function canManageCategory(
  capabilities: DocumentCapabilities,
  category: DocumentCategory,
): boolean {
  return category === 'CLINICAL'
    ? capabilities.canManageClinical
    : capabilities.canManageAdministrative;
}

export function canReadAnyDocument(capabilities: DocumentCapabilities): boolean {
  return DOCUMENT_CATEGORIES.some((category) => canReadCategory(capabilities, category));
}

export function readableCategories(capabilities: DocumentCapabilities): DocumentCategory[] {
  return DOCUMENT_CATEGORIES.filter((category) => canReadCategory(capabilities, category));
}

export function manageableCategories(capabilities: DocumentCapabilities): DocumentCategory[] {
  return DOCUMENT_CATEGORIES.filter((category) => canManageCategory(capabilities, category));
}
