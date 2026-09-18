'use client';

import { useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError } from '@/lib/api/problem';
import { useFocusFirstInvalid } from '@/lib/use-focus-first-invalid';

import { updateSettings, type ClinicSettings } from '../api';

const CURRENCY_PATTERN = /^[A-Z]{3}$/;

function isValidTimezone(value: string): boolean {
  try {
    return (Intl.supportedValuesOf('timeZone') as string[]).includes(value);
  } catch {
    return value.includes('/');
  }
}

export function settingsErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Você não tem permissão para editar as configurações.';
    }
    if (error.status === 422) {
      return 'Não foi possível salvar as configurações. Verifique os campos e tente novamente.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível salvar as configurações. Tente novamente.';
}

export function ClinicSettingsForm({
  clinicId,
  role,
  initialSettings,
}: {
  clinicId: string;
  role: string;
  initialSettings: ClinicSettings;
}) {
  const [displayName, setDisplayName] = useState(initialSettings.display_name);
  const [timezone, setTimezone] = useState(initialSettings.timezone);
  const [locale, setLocale] = useState(initialSettings.locale);
  const [currency, setCurrency] = useState(initialSettings.currency);
  const [fieldErrors, setFieldErrors] = useState<{
    displayName?: string;
    timezone?: string;
    locale?: string;
    currency?: string;
  }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  useFocusFirstInvalid(fieldErrors, formRef);

  const canManage = role === 'OWNER' || role === 'ADMIN';

  if (!canManage) {
    return (
      <dl className="app-panel grid gap-5 text-sm sm:grid-cols-2">
        <div className="rounded-lg bg-muted/55 p-4">
          <dt className="font-medium text-muted-foreground">Nome comercial</dt>
          <dd className="mt-1 font-semibold text-foreground">{initialSettings.display_name}</dd>
        </div>
        <div className="rounded-lg bg-muted/55 p-4">
          <dt className="font-medium text-muted-foreground">Fuso horário</dt>
          <dd className="mt-1 font-semibold text-foreground">{initialSettings.timezone}</dd>
        </div>
        <div className="rounded-lg bg-muted/55 p-4">
          <dt className="font-medium text-muted-foreground">Idioma</dt>
          <dd className="mt-1 font-semibold text-foreground">{initialSettings.locale}</dd>
        </div>
        <div className="rounded-lg bg-muted/55 p-4">
          <dt className="font-medium text-muted-foreground">Moeda</dt>
          <dd className="mt-1 font-semibold text-foreground">{initialSettings.currency}</dd>
        </div>
      </dl>
    );
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors: typeof fieldErrors = {};
    if (displayName.trim().length === 0) {
      errors.displayName = 'Informe o nome comercial.';
    } else if (displayName.trim().length > 200) {
      errors.displayName = 'O nome comercial deve ter no máximo 200 caracteres.';
    }
    if (!isValidTimezone(timezone)) {
      errors.timezone = 'Informe um fuso horário IANA válido.';
    }
    if (locale.trim().length < 2 || locale.trim().length > 10) {
      errors.locale = 'Informe um idioma entre 2 e 10 caracteres (ex.: pt-BR).';
    }
    if (!CURRENCY_PATTERN.test(currency)) {
      errors.currency = 'Use três letras maiúsculas (ex.: BRL).';
    }
    setFieldErrors(errors);
    setFormError(null);
    if (Object.keys(errors).length > 0) {
      setSaved(false);
      return;
    }

    setPending(true);
    try {
      await updateSettings(clinicId, {
        display_name: displayName.trim(),
        timezone,
        locale: locale.trim(),
        currency,
      });
      setSaved(true);
    } catch (error) {
      setSaved(false);
      setFormError(settingsErrorMessage(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      ref={formRef}
      onSubmit={handleSubmit}
      noValidate
      className="app-panel flex flex-col gap-5"
    >
      <div>
        <h2 className="font-semibold text-foreground">Operação da clínica</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Ajuste como nomes, datas e valores são exibidos para a equipe.
        </p>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="settings-display-name" className="app-label">
          Nome comercial
        </label>
        <input
          id="settings-display-name"
          name="display-name"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          aria-invalid={fieldErrors.displayName !== undefined}
          aria-describedby={
            fieldErrors.displayName !== undefined ? 'settings-display-name-error' : undefined
          }
          className="app-field"
        />
        {fieldErrors.displayName !== undefined && (
          <p id="settings-display-name-error" className="text-sm text-destructive">
            {fieldErrors.displayName}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="settings-timezone" className="app-label">
          Fuso horário
        </label>
        <input
          id="settings-timezone"
          name="timezone"
          list="settings-timezone-options"
          value={timezone}
          onChange={(event) => setTimezone(event.target.value)}
          aria-invalid={fieldErrors.timezone !== undefined}
          aria-describedby={
            fieldErrors.timezone !== undefined ? 'settings-timezone-error' : undefined
          }
          className="app-field"
        />
        <datalist id="settings-timezone-options">
          {(Intl.supportedValuesOf('timeZone') as string[]).map((zone) => (
            <option key={zone} value={zone} />
          ))}
        </datalist>
        {fieldErrors.timezone !== undefined && (
          <p id="settings-timezone-error" className="text-sm text-destructive">
            {fieldErrors.timezone}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="settings-locale" className="app-label">
          Idioma
        </label>
        <input
          id="settings-locale"
          name="locale"
          value={locale}
          onChange={(event) => setLocale(event.target.value)}
          aria-invalid={fieldErrors.locale !== undefined}
          aria-describedby={fieldErrors.locale !== undefined ? 'settings-locale-error' : undefined}
          className="app-field"
        />
        {fieldErrors.locale !== undefined && (
          <p id="settings-locale-error" className="text-sm text-destructive">
            {fieldErrors.locale}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="settings-currency" className="app-label">
          Moeda
        </label>
        <input
          id="settings-currency"
          name="currency"
          value={currency}
          maxLength={8}
          onChange={(event) => setCurrency(event.target.value)}
          aria-invalid={fieldErrors.currency !== undefined}
          aria-describedby={
            fieldErrors.currency !== undefined ? 'settings-currency-error' : undefined
          }
          className="app-field uppercase"
        />
        {fieldErrors.currency !== undefined && (
          <p id="settings-currency-error" className="text-sm text-destructive">
            {fieldErrors.currency}
          </p>
        )}
      </div>

      {formError !== null && <Feedback tone="error">{formError}</Feedback>}

      {saved && <Feedback tone="success">Configurações atualizadas.</Feedback>}

      <Button type="submit" disabled={pending} className="w-fit">
        {pending ? 'Salvando...' : 'Salvar configurações'}
      </Button>
    </form>
  );
}
