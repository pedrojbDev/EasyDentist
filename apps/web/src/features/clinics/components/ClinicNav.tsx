import { Building2, Settings, UserRound, Users } from 'lucide-react';
import Link from 'next/link';

import { cn } from '@/lib/utils';

const items = [
  { key: 'overview', label: 'Visão geral', suffix: '', icon: Building2 },
  { key: 'patients', label: 'Pacientes', suffix: '/patients', icon: UserRound },
  { key: 'settings', label: 'Ajustes', suffix: '/settings', icon: Settings },
  { key: 'members', label: 'Equipe', suffix: '/members', icon: Users },
] as const;

export function ClinicNav({
  clinicId,
  active,
}: {
  clinicId: string;
  active: (typeof items)[number]['key'];
}) {
  return (
    <nav
      aria-label="Seções da clínica"
      className="flex gap-1 overflow-x-auto border-b border-border"
    >
      {items.map((item) => {
        const Icon = item.icon;
        const selected = item.key === active;
        return (
          <Link
            key={item.key}
            href={`/clinics/${clinicId}${item.suffix}`}
            aria-current={selected ? 'page' : undefined}
            className={cn(
              'flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold transition-colors focus-visible:rounded-t-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25',
              selected
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:border-border hover:text-foreground',
            )}
          >
            <Icon aria-hidden="true" className="size-4" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
