'use client';

import { BellRing, Plus } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { StatusBadge } from '@/components/ui/status-badge';
import { ApiError } from '@/lib/api/problem';

import {
  createPatientAlert,
  updatePatientAlert,
  type PatientAlert,
  type PatientAlertKind,
} from '../api';
import { alertKindLabel, alertStatusLabel, formatDate } from '../labels';

const KIND_OPTIONS: PatientAlertKind[] = ['ALLERGY', 'MEDICATION', 'CLINICAL_RISK', 'OTHER'];

const KIND_TONES: Record<PatientAlertKind, 'danger' | 'warning' | 'neutral'> = {
  ALLERGY: 'danger',
  MEDICATION: 'warning',
  CLINICAL_RISK: 'danger',
  OTHER: 'neutral',
};

export function alertErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Você não tem permissão para gerenciar alertas clínicos.';
    }
    if (error.status === 404) {
      return 'Paciente não encontrado. Atualize a página.';
    }
    if (error.status === 422) {
      return 'Não foi possível salvar o alerta. Verifique os campos e tente novamente.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível salvar o alerta. Tente novamente.';
}

export function PatientAlertsPanel({
  clinicId,
  patientId,
  alerts,
  canManage,
}: {
  clinicId: string;
  patientId: string;
  alerts: PatientAlert[];
  canManage: boolean;
}) {
  const [rows, setRows] = useState(alerts);
  const [kind, setKind] = useState<PatientAlertKind>('ALLERGY');
  const [description, setDescription] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setFormError(null);
    if (!description.trim()) {
      setFieldError('Descreva o alerta clínico.');
      return;
    }
    setFieldError(null);
    setPending(true);
    try {
      const created = await createPatientAlert(clinicId, patientId, {
        kind,
        description: description.trim(),
      });
      setRows((current) => [created, ...current]);
      setDescription('');
      setKind('ALLERGY');
      setMessage('Alerta registrado.');
    } catch (cause) {
      setFormError(alertErrorMessage(cause));
    } finally {
      setPending(false);
    }
  }

  async function handleToggle(alert: PatientAlert) {
    setMessage(null);
    setFormError(null);
    const nextStatus = alert.status === 'ACTIVE' ? 'RESOLVED' : 'ACTIVE';
    try {
      const updated = await updatePatientAlert(clinicId, patientId, alert.id, {
        status: nextStatus,
      });
      setRows((current) => current.map((row) => (row.id === updated.id ? updated : row)));
      setMessage(nextStatus === 'RESOLVED' ? 'Alerta resolvido.' : 'Alerta reaberto.');
    } catch (cause) {
      setFormError(alertErrorMessage(cause));
    }
  }

  return (
    <section className="app-panel flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="grid size-10 shrink-0 place-items-center rounded-lg bg-destructive/10 text-destructive"
        >
          <BellRing className="size-5" />
        </span>
        <div>
          <h2 className="font-semibold text-foreground">Alertas clínicos</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Alergias, medicações e riscos que a equipe clínica precisa ver antes do atendimento.
          </p>
        </div>
      </div>

      {formError !== null && <Feedback tone="error">{formError}</Feedback>}
      {message !== null && <Feedback tone="success">{message}</Feedback>}

      {rows.length === 0 ? (
        <p className="rounded-lg bg-muted/55 p-4 text-sm text-muted-foreground">
          Nenhum alerta clínico registrado.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((alert) => (
            <li key={alert.id} className="rounded-lg border border-border bg-surface p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone={KIND_TONES[alert.kind]}>
                    {alertKindLabel(alert.kind)}
                  </StatusBadge>
                  <StatusBadge tone={alert.status === 'ACTIVE' ? 'info' : 'neutral'}>
                    {alertStatusLabel(alert.status)}
                  </StatusBadge>
                </div>
                {canManage && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => void handleToggle(alert)}
                  >
                    {alert.status === 'ACTIVE' ? 'Resolver' : 'Reabrir'}
                  </Button>
                )}
              </div>
              <p className="mt-3 whitespace-pre-line text-sm text-foreground">
                {alert.description}
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                Registrado em {formatDate(alert.created_at)}
                {alert.resolved_at !== null && ` · Resolvido em ${formatDate(alert.resolved_at)}`}
              </p>
            </li>
          ))}
        </ul>
      )}

      {canManage && (
        <form
          onSubmit={handleCreate}
          noValidate
          className="flex flex-col gap-3 border-t border-border pt-4"
        >
          <div className="grid gap-3 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
            <div className="flex flex-col gap-1">
              <label htmlFor="alert-kind" className="app-label">
                Tipo do alerta
              </label>
              <select
                id="alert-kind"
                name="alert-kind"
                value={kind}
                onChange={(event) => setKind(event.target.value as PatientAlertKind)}
                className="app-field"
              >
                {KIND_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {alertKindLabel(option)}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="alert-description" className="app-label">
                Descrição do alerta
              </label>
              <textarea
                id="alert-description"
                name="alert-description"
                value={description}
                rows={2}
                maxLength={500}
                onChange={(event) => setDescription(event.target.value)}
                aria-invalid={fieldError !== null}
                aria-describedby={fieldError !== null ? 'alert-description-error' : undefined}
                className="app-field"
              />
              {fieldError !== null && (
                <p id="alert-description-error" className="text-sm text-destructive">
                  {fieldError}
                </p>
              )}
            </div>
          </div>
          <Button type="submit" size="sm" disabled={pending} className="w-fit">
            <Plus aria-hidden="true" />
            {pending ? 'Adicionando...' : 'Adicionar alerta'}
          </Button>
        </form>
      )}
    </section>
  );
}
