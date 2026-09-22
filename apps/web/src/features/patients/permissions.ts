import type { components } from '@/lib/api/generated/schema';

export type Role = components['schemas']['Role'];

export type PatientCapabilities = {
  canCreate: boolean;
  canUpdate: boolean;
  canArchive: boolean;
  canReadAlerts: boolean;
  canManageAlerts: boolean;
};

const DENIED: PatientCapabilities = {
  canCreate: false,
  canUpdate: false,
  canArchive: false,
  canReadAlerts: false,
  canManageAlerts: false,
};

const CAPABILITIES: Record<string, PatientCapabilities> = {
  OWNER: {
    canCreate: true,
    canUpdate: true,
    canArchive: true,
    canReadAlerts: true,
    canManageAlerts: true,
  },
  ADMIN: {
    canCreate: true,
    canUpdate: true,
    canArchive: true,
    canReadAlerts: false,
    canManageAlerts: false,
  },
  DENTIST: {
    canCreate: false,
    canUpdate: false,
    canArchive: false,
    canReadAlerts: true,
    canManageAlerts: true,
  },
  ASSISTANT: {
    canCreate: false,
    canUpdate: false,
    canArchive: false,
    canReadAlerts: true,
    canManageAlerts: false,
  },
  RECEPTIONIST: {
    canCreate: true,
    canUpdate: true,
    canArchive: false,
    canReadAlerts: false,
    canManageAlerts: false,
  },
};

/** Mirrors the API RBAC matrix; anything unknown is denied. */
export function patientCapabilities(role: string): PatientCapabilities {
  return CAPABILITIES[role] ?? DENIED;
}
