import type { Route } from 'next';
import Link from 'next/link';

import { cn } from '@/lib/utils';

import { patientListHref } from '../params';

const tabs = [
  { status: 'ACTIVE' as const, label: 'Ativos' },
  { status: 'ARCHIVED' as const, label: 'Arquivados' },
];

export function PatientStatusTabs({
  clinicId,
  active,
  search,
}: {
  clinicId: string;
  active: 'ACTIVE' | 'ARCHIVED';
  search: string | null;
}) {
  return (
    <nav aria-label="Filtrar pacientes por situação" className="flex gap-2">
      {tabs.map((tab) => {
        const selected = tab.status === active;
        return (
          <Link
            key={tab.status}
            href={patientListHref(clinicId, { search, status: tab.status }) as Route}
            aria-current={selected ? 'page' : undefined}
            className={cn(
              'inline-flex min-h-9 items-center rounded-full border px-3.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25',
              selected
                ? 'border-primary/25 bg-accent text-accent-foreground'
                : 'border-border bg-surface text-muted-foreground hover:border-primary/30 hover:text-foreground',
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
