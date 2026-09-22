import { Search, X } from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';

import { Button } from '@/components/ui/button';

import { patientListHref, type PatientListQuery } from '../params';

export function PatientSearchForm({
  clinicId,
  query,
}: {
  clinicId: string;
  query: PatientListQuery;
}) {
  return (
    <form
      role="search"
      action={`/clinics/${clinicId}/patients`}
      method="get"
      className="app-panel flex flex-col gap-3 sm:flex-row sm:items-end"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <label htmlFor="patients-search" className="app-label">
          Buscar paciente
        </label>
        <input
          id="patients-search"
          name="search"
          type="search"
          defaultValue={query.search ?? ''}
          placeholder="Nome, CPF, telefone ou e-mail"
          maxLength={120}
          className="app-field"
        />
      </div>
      {query.status === 'ARCHIVED' && <input type="hidden" name="status" value="ARCHIVED" />}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit">
          <Search aria-hidden="true" />
          Buscar
        </Button>
        {query.search !== null && (
          <Button asChild variant="ghost">
            <Link href={patientListHref(clinicId, { status: query.status }) as Route}>
              <X aria-hidden="true" />
              Limpar busca
            </Link>
          </Button>
        )}
      </div>
    </form>
  );
}
