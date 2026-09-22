import { describe, expect, it } from 'vitest';

import { anamnesisCapabilities } from './permissions';

describe('anamnesisCapabilities', () => {
  it('mirrors the API RBAC matrix', () => {
    expect(anamnesisCapabilities('OWNER')).toEqual({
      canRead: true,
      canCreate: true,
      canUpdate: true,
      canFinalize: true,
    });
    expect(anamnesisCapabilities('DENTIST')).toEqual({
      canRead: true,
      canCreate: true,
      canUpdate: true,
      canFinalize: true,
    });
    expect(anamnesisCapabilities('ASSISTANT')).toEqual({
      canRead: true,
      canCreate: false,
      canUpdate: false,
      canFinalize: false,
    });
    expect(anamnesisCapabilities('ADMIN').canRead).toBe(false);
    expect(anamnesisCapabilities('RECEPTIONIST').canRead).toBe(false);
  });

  it('denies everything for unknown roles', () => {
    expect(anamnesisCapabilities('AUDITOR')).toEqual({
      canRead: false,
      canCreate: false,
      canUpdate: false,
      canFinalize: false,
    });
  });
});
