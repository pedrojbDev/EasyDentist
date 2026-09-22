import { FileClock } from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';

import { StatusBadge } from '@/components/ui/status-badge';

import type { Anamnesis } from '../api';
import { authorLabel, formatDateTime } from '../labels';

export function AnamnesisHistory({
  clinicId,
  patientId,
  versions,
}: {
  clinicId: string;
  patientId: string;
  versions: Anamnesis[];
}) {
  const finals = versions
    .filter((version) => version.status === 'FINAL')
    .sort((left, right) => (right.version_number ?? 0) - (left.version_number ?? 0));
  const latestNumber = finals[0]?.version_number ?? null;

  return (
    <section className="app-panel flex flex-col gap-4" aria-labelledby="anamnesis-history-title">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground"
        >
          <FileClock className="size-5" />
        </span>
        <div>
          <h2 id="anamnesis-history-title" className="font-semibold text-foreground">
            Histórico de versões
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Versões concluídas são imutáveis e preservam autoria e data.
          </p>
        </div>
      </div>

      {finals.length === 0 ? (
        <p className="rounded-lg bg-muted/55 p-4 text-sm text-muted-foreground">
          Nenhuma versão concluída registrada.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {finals.map((version) => (
            <li
              key={version.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone="success">Versão {version.version_number ?? '—'}</StatusBadge>
                  {version.version_number === latestNumber && (
                    <StatusBadge tone="info">Vigente</StatusBadge>
                  )}
                </div>
                <p className="mt-2 text-sm text-foreground">
                  {authorLabel(
                    version.author_professional_name,
                    version.author_cro_number,
                    version.author_cro_state,
                  ) ?? 'Autoria não registrada'}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {version.finalized_at !== null
                    ? `Concluída em ${formatDateTime(version.finalized_at)}`
                    : `Criada em ${formatDateTime(version.created_at)}`}
                </p>
              </div>
              <Link
                href={`/clinics/${clinicId}/patients/${patientId}/anamnesis/${version.id}` as Route}
                className="app-link text-sm font-semibold"
              >
                Ver versão
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
