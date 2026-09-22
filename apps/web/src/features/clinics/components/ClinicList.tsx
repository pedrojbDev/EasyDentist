'use client';

import { ArrowRight, Building2 } from 'lucide-react';
import Link from 'next/link';

import { StatusBadge } from '@/components/ui/status-badge';

import type { Clinic } from '../api';
import { roleLabel, statusLabel } from '../labels';

export function ClinicList({ clinics }: { clinics: Clinic[] }) {
  if (clinics.length === 0) {
    return (
      <div className="app-panel flex min-h-44 flex-col items-center justify-center text-center">
        <Building2 aria-hidden="true" className="mb-3 size-8 text-muted-foreground" />
        <p className="font-medium text-foreground">Você ainda não participa de nenhuma clínica.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Quando um vínculo estiver ativo, a clínica aparecerá aqui.
        </p>
      </div>
    );
  }

  return (
    <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {clinics.map((clinic) => (
        <li key={clinic.id}>
          <Link
            href={`/clinics/${clinic.id}`}
            className="group block h-full rounded-xl border border-border bg-surface p-5 shadow-[0_12px_35px_-26px_oklch(0.25_0.035_205_/_0.55)] transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-[0_18px_38px_-25px_oklch(0.25_0.035_205_/_0.6)] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25"
          >
            <span className="flex items-start justify-between gap-4">
              <span
                aria-hidden="true"
                className="grid size-11 shrink-0 place-items-center rounded-xl bg-accent text-sm font-bold text-accent-foreground"
              >
                {clinic.legal_name
                  .split(/\s+/)
                  .slice(0, 2)
                  .map((part) => part[0])
                  .join('')
                  .toUpperCase()}
              </span>
              <StatusBadge tone={clinic.status === 'ACTIVE' ? 'success' : 'warning'}>
                {statusLabel(clinic.status)}
              </StatusBadge>
            </span>
            <span className="mt-5 block font-semibold text-foreground">{clinic.legal_name}</span>
            <span className="mt-0.5 block text-sm text-muted-foreground">{clinic.slug}</span>
            <span className="mt-5 flex items-center justify-between gap-3 border-t border-border pt-4">
              <StatusBadge tone="info">{roleLabel(clinic.role)}</StatusBadge>
              <span className="inline-flex items-center gap-1 text-sm font-semibold text-primary">
                Acessar
                <ArrowRight
                  aria-hidden="true"
                  className="size-4 transition-transform group-hover:translate-x-0.5"
                />
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
