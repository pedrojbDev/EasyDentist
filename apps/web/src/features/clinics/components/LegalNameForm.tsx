'use client';

import { useMemo, useRef, useState } from 'react';

import { ApiError, GENERIC_ERROR_MESSAGE } from '@/lib/api/problem';
import { useFocusFirstInvalid } from '@/lib/use-focus-first-invalid';

import { updateClinic } from '../api';

const MAX_LEGAL_NAME_LENGTH = 200;

export function legalNameErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Você não tem permissão para editar a razão social.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível salvar a razão social. Tente novamente.';
}

export function LegalNameForm({
  clinicId,
  role,
  initialLegalName,
}: {
  clinicId: string;
  role: string;
  initialLegalName: string;
}) {
  const [legalName, setLegalName] = useState(initialLegalName);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const fieldErrors = useMemo(() => ({ legalName: fieldError ?? undefined }), [fieldError]);
  useFocusFirstInvalid(fieldErrors, formRef);

  if (role !== 'OWNER') {
    return null;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = legalName.trim();
    if (trimmed.length === 0) {
      setFieldError('Informe a razão social.');
      setSaved(false);
      return;
    }
    if (trimmed.length > MAX_LEGAL_NAME_LENGTH) {
      setFieldError('A razão social deve ter no máximo 200 caracteres.');
      setSaved(false);
      return;
    }
    setFieldError(null);
    setFormError(null);
    setPending(true);
    try {
      await updateClinic(clinicId, trimmed);
      setSaved(true);
    } catch (error) {
      setSaved(false);
      setFormError(legalNameErrorMessage(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="flex flex-col gap-3 rounded-lg border border-border p-4"
    >
      <div className="flex flex-col gap-1">
        <label htmlFor="legal-name" className="text-sm font-medium">
          Razão social
        </label>
        <input
          id="legal-name"
          name="legal-name"
          value={legalName}
          maxLength={MAX_LEGAL_NAME_LENGTH + 50}
          onChange={(event) => setLegalName(event.target.value)}
          aria-invalid={fieldError !== null}
          aria-describedby={fieldError !== null ? 'legal-name-error' : undefined}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm"
        />
        {fieldError !== null && (
          <p id="legal-name-error" className="text-sm text-destructive">
            {fieldError}
          </p>
        )}
      </div>

      {formError !== null && (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      )}

      {saved && (
        <p role="status" className="text-sm">
          Razão social atualizada.
        </p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="w-fit rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
      >
        {pending ? 'Salvando...' : 'Salvar razão social'}
      </button>
    </form>
  );
}
