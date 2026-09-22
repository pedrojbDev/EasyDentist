export type AnamnesisCapabilities = {
  canRead: boolean;
  canCreate: boolean;
  canUpdate: boolean;
  canFinalize: boolean;
};

const DENIED: AnamnesisCapabilities = {
  canRead: false,
  canCreate: false,
  canUpdate: false,
  canFinalize: false,
};

const CAPABILITIES: Record<string, AnamnesisCapabilities> = {
  OWNER: { canRead: true, canCreate: true, canUpdate: true, canFinalize: true },
  ADMIN: DENIED,
  DENTIST: { canRead: true, canCreate: true, canUpdate: true, canFinalize: true },
  ASSISTANT: { canRead: true, canCreate: false, canUpdate: false, canFinalize: false },
  RECEPTIONIST: DENIED,
};

/** Mirrors the API RBAC matrix; anything unknown is denied. */
export function anamnesisCapabilities(role: string): AnamnesisCapabilities {
  return CAPABILITIES[role] ?? DENIED;
}
