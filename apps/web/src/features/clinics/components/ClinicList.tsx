'use client';

import Link from 'next/link';

import type { Clinic } from '../api';

const ROLE_LABELS: Record<string, string> = {
  OWNER: 'Proprietário',
  ADMIN: 'Administrador',
  DENTIST: 'Dentista',
  ASSISTANT: 'Assistente',
  RECEPTIONIST: 'Recepcionista',
};

const STATUS_LABELS: Record<string, string> = {
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

export function ClinicList({ clinics }: { clinics: Clinic[] }) {
  if (clinics.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">Você ainda não participa de nenhuma clínica.</p>
    );
  }

  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {clinics.map((clinic) => (
        <li key={clinic.id}>
          <Link
            href={`/clinics/${clinic.id}`}
            className="block rounded-lg border border-border p-4 transition-colors hover:bg-muted"
          >
            <span className="font-medium">{clinic.legal_name}</span>
            <span className="block text-sm text-muted-foreground">{clinic.slug}</span>
            <span className="mt-2 flex gap-2 text-xs">
              <span className="rounded-full bg-muted px-2 py-0.5">{roleLabel(clinic.role)}</span>
              <span className="rounded-full bg-muted px-2 py-0.5">
                {statusLabel(clinic.status)}
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
