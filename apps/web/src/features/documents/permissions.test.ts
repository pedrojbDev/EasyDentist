import { describe, expect, it } from 'vitest';

import {
  canManageCategory,
  canReadAnyDocument,
  canReadCategory,
  documentCapabilities,
  manageableCategories,
} from './permissions';

describe('documentCapabilities', () => {
  it('mirrors the API RBAC matrix', () => {
    expect(documentCapabilities('OWNER')).toEqual({
      canReadAdministrative: true,
      canManageAdministrative: true,
      canReadClinical: true,
      canManageClinical: true,
    });
    expect(documentCapabilities('ADMIN')).toEqual({
      canReadAdministrative: true,
      canManageAdministrative: true,
      canReadClinical: false,
      canManageClinical: false,
    });
    expect(documentCapabilities('DENTIST')).toEqual({
      canReadAdministrative: true,
      canManageAdministrative: false,
      canReadClinical: true,
      canManageClinical: true,
    });
    expect(documentCapabilities('ASSISTANT')).toEqual({
      canReadAdministrative: true,
      canManageAdministrative: false,
      canReadClinical: true,
      canManageClinical: false,
    });
    expect(documentCapabilities('RECEPTIONIST')).toEqual({
      canReadAdministrative: true,
      canManageAdministrative: true,
      canReadClinical: false,
      canManageClinical: false,
    });
  });

  it('denies unknown roles by default', () => {
    expect(documentCapabilities('AUDITOR')).toEqual({
      canReadAdministrative: false,
      canManageAdministrative: false,
      canReadClinical: false,
      canManageClinical: false,
    });
  });

  it('answers category questions and lists manageable categories', () => {
    const dentist = documentCapabilities('DENTIST');
    expect(canReadAnyDocument(dentist)).toBe(true);
    expect(canReadCategory(dentist, 'CLINICAL')).toBe(true);
    expect(canReadCategory(dentist, 'ADMINISTRATIVE')).toBe(true);
    expect(canManageCategory(dentist, 'ADMINISTRATIVE')).toBe(false);
    expect(manageableCategories(dentist)).toEqual(['CLINICAL']);

    const receptionist = documentCapabilities('RECEPTIONIST');
    expect(manageableCategories(receptionist)).toEqual(['ADMINISTRATIVE']);
    expect(canReadAnyDocument(documentCapabilities('AUDITOR'))).toBe(false);
    expect(manageableCategories(documentCapabilities('AUDITOR'))).toEqual([]);
  });
});
