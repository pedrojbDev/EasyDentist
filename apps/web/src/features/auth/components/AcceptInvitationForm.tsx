'use client';

import Link from 'next/link';
import { useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError } from '@/lib/api/problem';
import { useFocusFirstInvalid } from '@/lib/use-focus-first-invalid';

import { acceptInvitation } from '../api';
import { useFragmentToken } from '../use-fragment-token';

const MIN_PASSWORD_LENGTH = 12;
const INVALID_INVITATION_MESSAGE = 'Convite inválido, expirado ou já utilizado.';
const FIRST_ACCESS_MESSAGE =
  'Não foi possível ativar o convite. Se este é o seu primeiro acesso, defina uma senha de 12 a 128 caracteres.';

export function acceptErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 400) {
      return INVALID_INVITATION_MESSAGE;
    }
    if (error.status === 422) {
      return FIRST_ACCESS_MESSAGE;
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível ativar o convite. Tente novamente.';
}

export function AcceptInvitationForm() {
  const token = useFragmentToken();
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [fieldErrors, setFieldErrors] = useState<{ password?: string; confirmation?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  useFocusFirstInvalid(fieldErrors, formRef);

  if (token === null) {
    return (
      <div className="flex flex-col gap-3">
        <Feedback tone="error">{INVALID_INVITATION_MESSAGE}</Feedback>
        <Link href="/login" className="app-link text-sm">
          Ir para o login
        </Link>
      </div>
    );
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (token === null) {
      return;
    }
    const wantsPassword = password.length > 0 || confirmation.length > 0;
    const errors: { password?: string; confirmation?: string } = {};
    if (wantsPassword) {
      if (password.length < MIN_PASSWORD_LENGTH || password.length > 128) {
        errors.password = 'A senha deve ter entre 12 e 128 caracteres.';
      }
      if (confirmation !== password) {
        errors.confirmation = 'As senhas não coincidem.';
      }
    }
    setFieldErrors(errors);
    setFormError(null);
    if (errors.password !== undefined || errors.confirmation !== undefined) {
      return;
    }

    setPending(true);
    try {
      if (wantsPassword) {
        await acceptInvitation(token, password);
      } else {
        await acceptInvitation(token);
      }
      setDone(true);
    } catch (error) {
      setFormError(acceptErrorMessage(error));
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <div className="flex flex-col gap-3">
        <Feedback tone="success">Convite aceito com sucesso.</Feedback>
        <Link href="/login" className="app-link text-sm">
          Entrar
        </Link>
      </div>
    );
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Se você já tem conta no EasyDentist, pode deixar a senha em branco: o convite apenas ativará
        seu acesso a esta clínica. Para o primeiro acesso, defina uma senha de 12 a 128 caracteres.
      </p>

      <div className="flex flex-col gap-1">
        <label htmlFor="accept-password" className="app-label">
          Senha (opcional)
        </label>
        <input
          id="accept-password"
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-invalid={fieldErrors.password !== undefined}
          aria-describedby={
            fieldErrors.password !== undefined ? 'accept-password-error' : undefined
          }
          className="app-field"
        />
        {fieldErrors.password !== undefined && (
          <p id="accept-password-error" className="text-sm text-destructive">
            {fieldErrors.password}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="accept-password-confirmation" className="app-label">
          Confirme a senha
        </label>
        <input
          id="accept-password-confirmation"
          name="password-confirmation"
          type="password"
          autoComplete="new-password"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          aria-invalid={fieldErrors.confirmation !== undefined}
          aria-describedby={
            fieldErrors.confirmation !== undefined ? 'accept-confirmation-error' : undefined
          }
          className="app-field"
        />
        {fieldErrors.confirmation !== undefined && (
          <p id="accept-confirmation-error" className="text-sm text-destructive">
            {fieldErrors.confirmation}
          </p>
        )}
      </div>

      {formError !== null && <Feedback tone="error">{formError}</Feedback>}

      <Button type="submit" size="lg" disabled={pending} className="w-full">
        {pending ? 'Ativando...' : 'Ativar convite'}
      </Button>
    </form>
  );
}
