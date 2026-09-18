'use client';

import Link from 'next/link';
import { useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError } from '@/lib/api/problem';
import { useFocusFirstInvalid } from '@/lib/use-focus-first-invalid';

import { resetPassword } from '../api';
import { useFragmentToken } from '../use-fragment-token';

const MIN_PASSWORD_LENGTH = 12;

const INVALID_LINK_MESSAGE = 'Link inválido ou expirado. Solicite uma nova recuperação.';

export function resetErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 400) {
      return INVALID_LINK_MESSAGE;
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível redefinir a senha. Tente novamente.';
}

export function InvalidLinkPanel() {
  return (
    <div className="flex flex-col gap-3">
      <Feedback tone="error">{INVALID_LINK_MESSAGE}</Feedback>
      <Link href="/forgot-password" className="app-link text-sm">
        Solicitar nova recuperação
      </Link>
    </div>
  );
}

export function ResetPasswordForm() {
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
    return <InvalidLinkPanel />;
  }

  async function submit() {
    if (token === null) {
      return;
    }
    const errors: { password?: string; confirmation?: string } = {};
    if (password.length < MIN_PASSWORD_LENGTH || password.length > 128) {
      errors.password = 'A senha deve ter entre 12 e 128 caracteres.';
    }
    if (confirmation !== password) {
      errors.confirmation = 'As senhas não coincidem.';
    }
    setFieldErrors(errors);
    setFormError(null);
    if (errors.password !== undefined || errors.confirmation !== undefined) {
      return;
    }

    setPending(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (error) {
      setFormError(resetErrorMessage(error));
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <div className="flex flex-col gap-3">
        <Feedback tone="success">Senha alterada com sucesso.</Feedback>
        <Link href="/login" className="app-link text-sm">
          Entrar
        </Link>
      </div>
    );
  }

  return (
    <form
      ref={formRef}
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
      noValidate
      className="flex flex-col gap-4"
    >
      <div className="flex flex-col gap-1">
        <label htmlFor="reset-password" className="app-label">
          Nova senha
        </label>
        <input
          id="reset-password"
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-invalid={fieldErrors.password !== undefined}
          aria-describedby={fieldErrors.password !== undefined ? 'reset-password-error' : undefined}
          className="app-field"
        />
        {fieldErrors.password !== undefined && (
          <p id="reset-password-error" className="text-sm text-destructive">
            {fieldErrors.password}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="reset-password-confirmation" className="app-label">
          Confirme a nova senha
        </label>
        <input
          id="reset-password-confirmation"
          name="password-confirmation"
          type="password"
          autoComplete="new-password"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          aria-invalid={fieldErrors.confirmation !== undefined}
          aria-describedby={
            fieldErrors.confirmation !== undefined ? 'reset-confirmation-error' : undefined
          }
          className="app-field"
        />
        {fieldErrors.confirmation !== undefined && (
          <p id="reset-confirmation-error" className="text-sm text-destructive">
            {fieldErrors.confirmation}
          </p>
        )}
      </div>

      {formError !== null && <Feedback tone="error">{formError}</Feedback>}

      <Button type="submit" size="lg" disabled={pending} className="w-full">
        {pending ? 'Redefinindo...' : 'Redefinir senha'}
      </Button>

      {formError !== null && (
        <Button type="button" variant="outline" disabled={pending} onClick={() => void submit()}>
          Tentar novamente
        </Button>
      )}
    </form>
  );
}
