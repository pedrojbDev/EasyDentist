'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { roleLabel } from '@/features/clinics/components/ClinicList';
import { ApiError } from '@/lib/api/problem';

import { inviteMember, type Role } from '../api';

const ALL_ROLES: Role[] = ['OWNER', 'ADMIN', 'DENTIST', 'ASSISTANT', 'RECEPTIONIST'];
const NON_MANAGER_ROLES: Role[] = ['DENTIST', 'ASSISTANT', 'RECEPTIONIST'];
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const expiryFormatter = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' });

export function inviteErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Você não tem permissão para convidar para esta clínica.';
    }
    if (error.status === 409) {
      return 'Este e-mail já participa da clínica.';
    }
    if (error.status === 422) {
      return 'Não foi possível enviar o convite. Verifique os dados e tente novamente.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível enviar o convite. Tente novamente.';
}

export function InviteMemberForm({ clinicId, actorRole }: { clinicId: string; actorRole: Role }) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<Role>('DENTIST');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<{ email: string; expiresAt: string } | null>(null);
  const [pending, setPending] = useState(false);

  if (actorRole !== 'OWNER' && actorRole !== 'ADMIN') {
    return null;
  }
  const options = actorRole === 'OWNER' ? ALL_ROLES : NON_MANAGER_ROLES;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = email.trim();
    if (trimmed.length === 0) {
      setFieldError('Informe o e-mail do convidado.');
      return;
    }
    if (!EMAIL_PATTERN.test(trimmed)) {
      setFieldError('Informe um e-mail válido.');
      return;
    }
    setFieldError(null);
    setFormError(null);
    setSentTo(null);
    setPending(true);
    try {
      const invitation = await inviteMember(clinicId, trimmed, role);
      setSentTo({ email: trimmed, expiresAt: invitation.invitation_expires_at });
      setEmail('');
    } catch (error) {
      setFormError(inviteErrorMessage(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="app-panel flex flex-col gap-4 xl:sticky xl:top-6"
    >
      <div>
        <h2 className="font-semibold text-foreground">Convidar pessoa</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Envie um convite e defina o papel inicial.
        </p>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="invite-email" className="app-label">
          E-mail do convidado
        </label>
        <input
          id="invite-email"
          name="invite-email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={fieldError !== null}
          aria-describedby={fieldError !== null ? 'invite-email-error' : undefined}
          className="app-field"
        />
        {fieldError !== null && (
          <p id="invite-email-error" className="text-sm text-destructive">
            {fieldError}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="invite-role" className="app-label">
          Papel do convidado
        </label>
        <select
          id="invite-role"
          name="invite-role"
          value={role}
          onChange={(event) => setRole(event.target.value as Role)}
          className="app-field"
        >
          {options.map((option) => (
            <option key={option} value={option}>
              {roleLabel(option)}
            </option>
          ))}
        </select>
      </div>

      {formError !== null && <Feedback tone="error">{formError}</Feedback>}

      {sentTo !== null && (
        <Feedback tone="success">
          Convite enviado para {sentTo.email}. O link expira em{' '}
          {expiryFormatter.format(new Date(sentTo.expiresAt))}.
        </Feedback>
      )}

      <Button type="submit" disabled={pending} className="w-full xl:w-fit">
        {pending ? 'Enviando...' : 'Enviar convite'}
      </Button>
    </form>
  );
}
