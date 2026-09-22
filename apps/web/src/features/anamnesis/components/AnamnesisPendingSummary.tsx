import { CheckCircle2, ListChecks } from 'lucide-react';

import { StatusBadge } from '@/components/ui/status-badge';

import type { PendingQuestion } from '../answers';
import { sectionAnchorId } from '../catalog';

type PendingGroup = {
  sectionId: string;
  sectionTitle: string;
  count: number;
  details: number;
};

function groupPending(pending: PendingQuestion[]): PendingGroup[] {
  const groups: PendingGroup[] = [];
  for (const item of pending) {
    const current = groups.at(-1);
    if (current !== undefined && current.sectionId === item.sectionId) {
      current.count += 1;
      current.details += item.reason === 'details' ? 1 : 0;
      continue;
    }
    groups.push({
      sectionId: item.sectionId,
      sectionTitle: item.sectionTitle,
      count: 1,
      details: item.reason === 'details' ? 1 : 0,
    });
  }
  return groups;
}

export function AnamnesisPendingSummary({
  pending,
  answered,
  total,
}: {
  pending: PendingQuestion[];
  answered: number;
  total: number;
}) {
  const groups = groupPending(pending);
  const complete = pending.length === 0;

  return (
    <section className="app-panel flex flex-col gap-3" aria-labelledby="anamnesis-pending-title">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className={
              complete
                ? 'grid size-9 place-items-center rounded-lg bg-success/15 text-foreground'
                : 'grid size-9 place-items-center rounded-lg bg-warning/20 text-foreground'
            }
          >
            {complete ? <CheckCircle2 className="size-5" /> : <ListChecks className="size-5" />}
          </span>
          <h2 id="anamnesis-pending-title" className="font-semibold text-foreground">
            Pendências
          </h2>
        </div>
        <StatusBadge tone={complete ? 'success' : 'warning'}>
          {answered}/{total} respondidas
        </StatusBadge>
      </div>

      {complete ? (
        <p className="text-sm text-muted-foreground">
          Todas as perguntas estão respondidas. A anamnese pode ser concluída.
        </p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            {pending.length === 1
              ? 'Falta 1 item para concluir.'
              : `Faltam ${pending.length} itens para concluir.`}
          </p>
          <ul className="flex flex-col gap-1.5 text-sm">
            {groups.map((group) => (
              <li key={group.sectionId} className="flex items-baseline justify-between gap-3">
                <a href={`#${sectionAnchorId(group.sectionId)}`} className="app-link">
                  {group.sectionTitle}
                </a>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {group.count}
                  {group.details > 0 ? ` · ${group.details} complemento(s)` : ''}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
