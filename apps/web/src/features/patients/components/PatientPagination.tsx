import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';

import { Button } from '@/components/ui/button';

import { patientListHref, type PatientListQuery } from '../params';

export function PatientPagination({
  clinicId,
  query,
  total,
}: {
  clinicId: string;
  query: PatientListQuery;
  total: number;
}) {
  const start = total === 0 ? 0 : query.offset + 1;
  const end = Math.min(query.offset + query.limit, total);
  const hasPrevious = query.page > 1;
  const hasNext = query.offset + query.limit < total;
  const linkQuery = { search: query.search, status: query.status };

  return (
    <nav
      aria-label="Paginação de pacientes"
      className="flex flex-wrap items-center justify-between gap-3"
    >
      <p className="text-sm text-muted-foreground">
        Mostrando {start}–{end} de {total} pacientes
      </p>
      <div className="flex flex-wrap gap-2">
        {hasPrevious && (
          <Button asChild variant="outline" size="sm">
            <Link
              href={patientListHref(clinicId, { ...linkQuery, page: query.page - 1 }) as Route}
              aria-label="Página anterior"
            >
              <ChevronLeft aria-hidden="true" />
              Anterior
            </Link>
          </Button>
        )}
        {hasNext && (
          <Button asChild variant="outline" size="sm">
            <Link
              href={patientListHref(clinicId, { ...linkQuery, page: query.page + 1 }) as Route}
              aria-label="Próxima página"
            >
              Próxima
              <ChevronRight aria-hidden="true" />
            </Link>
          </Button>
        )}
      </div>
    </nav>
  );
}
