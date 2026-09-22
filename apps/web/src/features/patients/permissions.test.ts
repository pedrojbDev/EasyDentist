import { describe, expect, it } from 'vitest';

import { patientCapabilities } from './permissions';

describe('patientCapabilities', () => {
  it('mirrors the API RBAC matrix for every role', () => {
    expect(patientCapabilities('OWNER')).toEqual({
      canCreate: true,
      canUpdate: true,
      canArchive: true,
      canReadAlerts: true,
      canManageAlerts: true,
    });
    expect(patientCapabilities('ADMIN')).toEqual({
      canCreate: true,
      canUpdate: true,
      canArchive: true,
      canReadAlerts: false,
      canManageAlerts: false,
    });
    expect(patientCapabilities('DENTIST')).toEqual({
      canCreate: false,
      canUpdate: false,
      canArchive: false,
      canReadAlerts: true,
      canManageAlerts: true,
    });
    expect(patientCapabilities('ASSISTANT')).toEqual({
      canCreate: false,
      canUpdate: false,
      canArchive: false,
      canReadAlerts: true,
      canManageAlerts: false,
    });
    expect(patientCapabilities('RECEPTIONIST')).toEqual({
      canCreate: true,
      canUpdate: true,
      canArchive: false,
      canReadAlerts: false,
      canManageAlerts: false,
    });
  });

  it('denies everything to unknown roles', () => {
    expect(patientCapabilities('AUDITOR')).toEqual({
      canCreate: false,
      canUpdate: false,
      canArchive: false,
      canReadAlerts: false,
      canManageAlerts: false,
    });
  });
});
