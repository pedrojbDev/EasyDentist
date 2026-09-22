export const ROLE_LABELS: Record<string, string> = {
  OWNER: 'Proprietário',
  ADMIN: 'Administrador',
  DENTIST: 'Dentista',
  ASSISTANT: 'Assistente',
  RECEPTIONIST: 'Recepcionista',
};

export const STATUS_LABELS: Record<string, string> = {
  PROVISIONING: 'Em provisionamento',
  ACTIVE: 'Ativa',
  SUSPENDED: 'Suspensa',
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}
