'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ConfirmButton } from '@/components/ui/confirm-button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError } from '@/lib/api/problem';

import { archivePatient, restorePatient } from '../api';

export function archiveErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Você não tem permissão para arquivar ou restaurar pacientes.';
    }
    if (error.status === 404) {
      return 'Paciente não encontrado. Atualize a página.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível concluir a ação. Tente novamente.';
}

export function PatientArchiveButton({
  clinicId,
  patientId,
  patientName,
  archived,
}: {
  clinicId: string;
  patientId: string;
  patientName: string;
  archived: boolean;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const label = archived ? 'Restaurar' : 'Arquivar';

  async function handleConfirm() {
    setError(null);
    setPending(true);
    try {
      if (archived) {
        await restorePatient(clinicId, patientId);
      } else {
        await archivePatient(clinicId, patientId);
      }
      router.refresh();
    } catch (cause) {
      setError(archiveErrorMessage(cause));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="inline-flex flex-col items-start gap-1">
      <ConfirmButton
        message={
          archived
            ? `Restaurar ${patientName}? O paciente voltará para a lista de ativos.`
            : `Arquivar ${patientName}? O histórico clínico será preservado.`
        }
        onConfirm={() => void handleConfirm()}
        ariaLabel={`${label} ${patientName}`}
        variant="outline"
        size="sm"
      >
        {pending ? 'Aguarde...' : label}
      </ConfirmButton>
      {error !== null && (
        <Feedback tone="error" className="mt-1">
          {error}
        </Feedback>
      )}
    </div>
  );
}
