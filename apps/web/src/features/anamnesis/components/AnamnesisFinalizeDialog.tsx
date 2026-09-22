'use client';

import { ShieldCheck } from 'lucide-react';

import { Button } from '@/components/ui/button';

import type { ProfessionalProfile } from '../api';

export function AnamnesisFinalizeDialog({
  open,
  patientName,
  profile,
  onCancel,
  onConfirm,
  pending,
}: {
  open: boolean;
  patientName: string;
  profile: ProfessionalProfile;
  onCancel: () => void;
  onConfirm: () => void;
  pending: boolean;
}) {
  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-foreground/40 p-4"
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="anamnesis-finalize-title"
        className="app-panel w-full max-w-lg bg-surface"
      >
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground"
          >
            <ShieldCheck className="size-5" />
          </span>
          <div>
            <h2 id="anamnesis-finalize-title" className="font-semibold text-foreground">
              Concluir anamnese
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              A anamnese de <strong className="text-foreground">{patientName}</strong> será
              registrada como uma nova versão imutável, com autoria e data.
            </p>
          </div>
        </div>

        <dl className="mt-4 flex flex-col gap-2 rounded-lg bg-muted/55 p-3 text-sm">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">Profissional</dt>
            <dd className="text-right font-medium text-foreground">{profile.professional_name}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">CRO</dt>
            <dd className="text-right font-medium text-foreground">
              {profile.cro_number}/{profile.cro_state}
            </dd>
          </div>
        </dl>

        <p className="mt-4 text-sm text-muted-foreground">
          Concluir registra autoria, data e o perfil profissional informado, mas não é assinatura
          digital e não substitui a ciência ou a assinatura do paciente.
        </p>

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onCancel} disabled={pending}>
            Cancelar
          </Button>
          <Button type="button" onClick={onConfirm} disabled={pending}>
            {pending ? 'Concluindo...' : 'Concluir anamnese'}
          </Button>
        </div>
      </div>
    </div>
  );
}
