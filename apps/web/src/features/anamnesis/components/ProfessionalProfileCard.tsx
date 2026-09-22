'use client';

import { IdCard, Pencil } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError } from '@/lib/api/problem';

import { saveProfessionalProfile, type ProfessionalProfile } from '../api';

const CRO_DISCLAIMER =
  'O EasyDentist registra o CRO informado e não valida o número em base externa do CFO.';

export function professionalProfileErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) {
      return 'Verifique nome profissional, número do CRO e UF.';
    }
    if (error.status === 401) {
      return 'Sessão expirada. Entre novamente.';
    }
    if (error.status === 429) {
      return 'Muitas tentativas. Tente novamente em instantes.';
    }
  }
  return 'Não foi possível salvar o perfil profissional. Tente novamente.';
}

export function ProfessionalProfileCard({
  profile: initialProfile,
  onSaved,
}: {
  profile: ProfessionalProfile | null;
  onSaved?: (profile: ProfessionalProfile) => void;
}) {
  const [profile, setProfile] = useState(initialProfile);
  const [editing, setEditing] = useState(initialProfile === null);
  const [name, setName] = useState(initialProfile?.professional_name ?? '');
  const [croNumber, setCroNumber] = useState(initialProfile?.cro_number ?? '');
  const [croState, setCroState] = useState(initialProfile?.cro_state ?? '');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!name.trim() || !croNumber.trim() || !/^[A-Za-z]{2}$/.test(croState.trim())) {
      setFieldError('Informe nome profissional, número do CRO e UF com duas letras.');
      return;
    }
    setFieldError(null);
    setPending(true);
    try {
      const saved = await saveProfessionalProfile({
        professional_name: name.trim(),
        cro_number: croNumber.trim(),
        cro_state: croState.trim().toUpperCase(),
      });
      setProfile(saved);
      setEditing(false);
      onSaved?.(saved);
    } catch (cause) {
      setError(professionalProfileErrorMessage(cause));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="app-panel flex flex-col gap-3" aria-labelledby="professional-profile-title">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground"
        >
          <IdCard className="size-5" />
        </span>
        <div className="min-w-0">
          <h2 id="professional-profile-title" className="font-semibold text-foreground">
            Perfil profissional
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Usado como autoria e snapshot nas anamneses concluídas.
          </p>
        </div>
      </div>

      {error !== null && <Feedback tone="error">{error}</Feedback>}

      {profile !== null && !editing ? (
        <>
          <dl className="flex flex-col gap-1 text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-muted-foreground">Nome</dt>
              <dd className="text-right font-medium text-foreground">
                {profile.professional_name}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-muted-foreground">CRO</dt>
              <dd className="text-right font-medium text-foreground">
                {profile.cro_number}/{profile.cro_state}
              </dd>
            </div>
          </dl>
          <p className="text-xs text-muted-foreground">{CRO_DISCLAIMER}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-fit"
            onClick={() => setEditing(true)}
          >
            <Pencil aria-hidden="true" />
            Editar perfil profissional
          </Button>
        </>
      ) : (
        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="professional-name" className="app-label">
              Nome profissional
            </label>
            <input
              id="professional-name"
              name="professional-name"
              value={name}
              maxLength={200}
              onChange={(event) => setName(event.target.value)}
              className="app-field"
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_6rem]">
            <div className="flex flex-col gap-1">
              <label htmlFor="professional-cro-number" className="app-label">
                Número do CRO
              </label>
              <input
                id="professional-cro-number"
                name="professional-cro-number"
                value={croNumber}
                maxLength={30}
                onChange={(event) => setCroNumber(event.target.value)}
                className="app-field"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="professional-cro-state" className="app-label">
                UF
              </label>
              <input
                id="professional-cro-state"
                name="professional-cro-state"
                value={croState}
                maxLength={2}
                placeholder="BA"
                onChange={(event) => setCroState(event.target.value.toUpperCase())}
                className="app-field"
              />
            </div>
          </div>
          {fieldError !== null && <p className="text-sm text-destructive">{fieldError}</p>}
          <p className="text-xs text-muted-foreground">{CRO_DISCLAIMER}</p>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" disabled={pending} className="w-fit">
              {pending ? 'Salvando...' : 'Salvar perfil profissional'}
            </Button>
            {profile !== null && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditing(false);
                  setFieldError(null);
                  setError(null);
                }}
              >
                Cancelar
              </Button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
