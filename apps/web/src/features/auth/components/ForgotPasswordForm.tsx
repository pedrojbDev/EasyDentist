'use client';

import Link from 'next/link';
import { useMemo, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError, GENERIC_ERROR_MESSAGE } from '@/lib/api/problem';
import { useFocusFirstInvalid } from '@/lib/use-focus-first-invalid';

import { forgotPassword } from '../api';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const CONFIRMATION =
  'Se existir uma conta com este e-mail, enviaremos as instruções de recuperação. Verifique sua caixa de entrada e o spam.';

export function forgotErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    return error.retryAfter === undefined
      ? 'Muitas tentativas. Tente novamente em instantes.'
      : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
  }
  return GENERIC_ERROR_MESSAGE;
}

export function ForgotPasswordForm() {
  const [email, setEmail] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [pending, setPending] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const fieldErrors = useMemo(() => ({ email: fieldError ?? undefined }), [fieldError]);
  useFocusFirstInvalid(fieldErrors, formRef);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = email.trim();
    if (trimmed.length === 0) {
      setFieldError('Informe seu e-mail.');
      return;
    }
    if (!EMAIL_PATTERN.test(trimmed)) {
      setFieldError('Informe um e-mail válido.');
      return;
    }
    setFieldError(null);
    setFormError(null);
    setPending(true);
    try {
      await forgotPassword(trimmed);
      setSent(true);
    } catch (error) {
      setFormError(forgotErrorMessage(error));
    } finally {
      setPending(false);
    }
  }

  if (sent) {
    return (
      <div className="flex flex-col gap-4">
        <Feedback tone="success">{CONFIRMATION}</Feedback>
        <Link href="/login" className="app-link text-sm">
          Voltar para o login
        </Link>
      </div>
    );
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="forgot-email" className="app-label">
          E-mail
        </label>
        <input
          id="forgot-email"
          name="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={fieldError !== null}
          aria-describedby={fieldError !== null ? 'forgot-email-error' : undefined}
          className="app-field"
        />
        {fieldError !== null && (
          <p id="forgot-email-error" className="text-sm text-destructive">
            {fieldError}
          </p>
        )}
      </div>

      {formError !== null && <Feedback tone="error">{formError}</Feedback>}

      <Button type="submit" size="lg" disabled={pending} className="w-full">
        {pending ? 'Enviando...' : 'Enviar instruções'}
      </Button>
    </form>
  );
}
