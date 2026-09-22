'use client';

import { FilePlus2, RefreshCw } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { ConfirmButton } from '@/components/ui/confirm-button';
import { Feedback } from '@/components/ui/feedback';

import { createAnamnesis, type Anamnesis } from '../api';
import { anamnesisErrorMessage } from './AnamnesisForm';

export function AnamnesisStartActions({
  clinicId,
  patientId,
  latestFinal,
}: {
  clinicId: string;
  patientId: string;
  latestFinal: Anamnesis | null;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start(baseVersionId?: string) {
    setPending(true);
    setError(null);
    try {
      await createAnamnesis(
        clinicId,
        patientId,
        baseVersionId === undefined ? {} : { base_version_id: baseVersionId },
      );
      router.refresh();
    } catch (cause) {
      setError(anamnesisErrorMessage(cause));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="app-panel flex flex-col gap-3" aria-labelledby="anamnesis-start-title">
      <div>
        <h2 id="anamnesis-start-title" className="font-semibold text-foreground">
          Nenhum rascunho em andamento
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {latestFinal === null
            ? 'Inicie a anamnese para registrar queixa, histórias e inventário odontológico.'
            : `A versão vigente é a ${latestFinal.version_number ?? '—'}. Inicie uma revisão a partir dela ou comece em branco.`}
        </p>
      </div>

      {error !== null && <Feedback tone="error">{error}</Feedback>}

      <div className="flex flex-wrap gap-2">
        {latestFinal !== null && (
          <Button type="button" disabled={pending} onClick={() => void start(latestFinal.id)}>
            <RefreshCw aria-hidden="true" />
            {pending ? 'Iniciando...' : `Iniciar revisão da versão ${latestFinal.version_number}`}
          </Button>
        )}
        {latestFinal === null ? (
          <Button type="button" disabled={pending} onClick={() => void start()}>
            <FilePlus2 aria-hidden="true" />
            {pending ? 'Iniciando...' : 'Iniciar anamnese'}
          </Button>
        ) : (
          <ConfirmButton
            message="Iniciar um rascunho em branco, sem copiar a versão vigente?"
            onConfirm={() => void start()}
            variant="outline"
          >
            <FilePlus2 aria-hidden="true" />
            Iniciar em branco
          </ConfirmButton>
        )}
      </div>
    </section>
  );
}

export function AnamnesisRevisionButton({
  clinicId,
  patientId,
  baseVersionId,
}: {
  clinicId: string;
  patientId: string;
  baseVersionId: string;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setPending(true);
    setError(null);
    try {
      await createAnamnesis(clinicId, patientId, { base_version_id: baseVersionId });
      router.push(`/clinics/${clinicId}/patients/${patientId}/anamnesis`);
      router.refresh();
    } catch (cause) {
      setError(anamnesisErrorMessage(cause));
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {error !== null && <Feedback tone="error">{error}</Feedback>}
      <Button type="button" disabled={pending} onClick={() => void start()} className="w-fit">
        <RefreshCw aria-hidden="true" />
        {pending ? 'Iniciando...' : 'Iniciar revisão desta versão'}
      </Button>
    </div>
  );
}
