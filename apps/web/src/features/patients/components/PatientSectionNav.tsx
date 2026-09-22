import { ClipboardList, FileText, IdCard } from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';

import { StatusBadge } from '@/components/ui/status-badge';
import { cn } from '@/lib/utils';

type SectionKey = 'record' | 'anamnesis' | 'documents';

const items: {
  key: SectionKey;
  label: string;
  icon: typeof IdCard;
  href?: (clinicId: string, patientId: string) => string;
}[] = [
  {
    key: 'record',
    label: 'Dados cadastrais',
    icon: IdCard,
    href: (clinicId, patientId) => `/clinics/${clinicId}/patients/${patientId}`,
  },
  {
    key: 'anamnesis',
    label: 'Anamnese',
    icon: ClipboardList,
    href: (clinicId, patientId) => `/clinics/${clinicId}/patients/${patientId}/anamnesis`,
  },
  { key: 'documents', label: 'Documentos', icon: FileText },
];

/**
 * Local navigation of the patient record. Anamnese is a real section; documents
 * is the M2.5 extension slot and administrative roles never see clinical tabs.
 */
export function PatientSectionNav({
  clinicId,
  patientId,
  active,
  canReadAnamnesis,
}: {
  clinicId: string;
  patientId: string;
  active: SectionKey;
  canReadAnamnesis: boolean;
}) {
  const visible = items.filter((item) => item.key !== 'anamnesis' || canReadAnamnesis);

  return (
    <nav
      aria-label="Seções do paciente"
      className="flex gap-1 overflow-x-auto border-b border-border"
    >
      {visible.map((item) => {
        const Icon = item.icon;
        const selected = item.key === active;
        const className = cn(
          'flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold transition-colors',
          selected ? 'border-primary text-primary' : 'border-transparent text-muted-foreground',
        );
        if (item.href === undefined) {
          return (
            <span
              key={item.key}
              aria-disabled="true"
              className={cn(className, 'cursor-not-allowed opacity-60')}
            >
              <Icon aria-hidden="true" className="size-4" />
              {item.label}
              <StatusBadge tone="neutral">Em breve</StatusBadge>
            </span>
          );
        }
        return (
          <Link
            key={item.key}
            href={item.href(clinicId, patientId) as Route}
            aria-current={selected ? 'page' : undefined}
            className={cn(
              className,
              'hover:border-border hover:text-foreground focus-visible:rounded-t-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25',
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
