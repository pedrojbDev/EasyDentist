'use client';

import { useRouter } from 'next/navigation';
import { useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError, GENERIC_ERROR_MESSAGE } from '@/lib/api/problem';
import { useFocusFirstInvalid } from '@/lib/use-focus-first-invalid';

import { login } from '../api';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type FieldErrors = { email?: string; password?: string };

function validate(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {};
  const trimmed = email.trim();
  if (trimmed.length === 0) {
    errors.email = 'Informe seu e-mail.';
  } else if (!EMAIL_PATTERN.test(trimmed)) {
    errors.email = 'Informe um e-mail válido.';
  }
  if (password.length === 0) {
    errors.password = 'Informe sua senha.';
  }
  return errors;
}

export function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return 'E-mail ou senha inválidos.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return GENERIC_ERROR_MESSAGE;
}

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  useFocusFirstInvalid(fieldErrors, formRef);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validate(email, password);
    setFieldErrors(errors);
    setFormError(null);
    if (errors.email !== undefined || errors.password !== undefined) {
      return;
    }

    setPending(true);
    try {
      await login(email.trim(), password);
      router.replace('/clinics');
      router.refresh();
    } catch (error) {
      setFormError(loginErrorMessage(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="login-email" className="app-label">
          E-mail
        </label>
        <input
          id="login-email"
          name="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={fieldErrors.email !== undefined}
          aria-describedby={fieldErrors.email !== undefined ? 'login-email-error' : undefined}
          className="app-field"
        />
        {fieldErrors.email !== undefined && (
          <p id="login-email-error" className="text-sm text-destructive">
            {fieldErrors.email}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="login-password" className="app-label">
          Senha
        </label>
        <input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-invalid={fieldErrors.password !== undefined}
          aria-describedby={fieldErrors.password !== undefined ? 'login-password-error' : undefined}
          className="app-field"
        />
        {fieldErrors.password !== undefined && (
          <p id="login-password-error" className="text-sm text-destructive">
            {fieldErrors.password}
          </p>
        )}
      </div>

      {formError !== null && <Feedback tone="error">{formError}</Feedback>}

      <Button type="submit" size="lg" disabled={pending} className="w-full">
        {pending ? 'Entrando...' : 'Entrar'}
      </Button>
    </form>
  );
}
