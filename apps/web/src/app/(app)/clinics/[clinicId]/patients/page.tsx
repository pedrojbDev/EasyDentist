import { Plus } from 'lucide-react';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { getClinicOnServer } from '@/features/clinics/server';
import { PatientPagination } from '@/features/patients/components/PatientPagination';
import { PatientSearchForm } from '@/features/patients/components/PatientSearchForm';
import { PatientStatusTabs } from '@/features/patients/components/PatientStatusTabs';
import { PatientTable } from '@/features/patients/components/PatientTable';
import { parsePatientListParams } from '@/features/patients/params';
import { patientCapabilities } from '@/features/patients/permissions';
import { listPatientsOnServer } from '@/features/patients/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function PatientsPage({
  params,
  searchParams,
}: {
  params: Promise<{ clinicId: string }>;
  searchParams: SearchParams;
}) {
  const { clinicId } = await params;
  const query = parsePatientListParams(await searchParams);

  let clinic;
  let page;
  try {
    clinic = await getClinicOnServer(clinicId);
    page = await listPatientsOnServer(clinicId, {
      search: query.search,
      status: query.status,
      limit: query.limit,
      offset: query.offset,
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  const capabilities = patientCapabilities(clinic.role);

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow={clinic.legal_name}
        title="Pacientes"
        description="Cadastro operacional, busca e alertas clínicos desta clínica."
        actions={
          capabilities.canCreate ? (
            <Button asChild>
              <Link href={`/clinics/${clinic.id}/patients/new`}>
                <Plus aria-hidden="true" />
                Novo paciente
              </Link>
            </Button>
          ) : undefined
        }
      />
      <ClinicNav clinicId={clinic.id} active="patients" />
      <div className="flex flex-col gap-4">
        <PatientSearchForm clinicId={clinic.id} query={query} />
        <PatientStatusTabs clinicId={clinic.id} active={query.status} search={query.search} />
        <PatientTable clinicId={clinic.id} patients={page.items} capabilities={capabilities} />
        <PatientPagination clinicId={clinic.id} query={query} total={page.total} />
      </div>
    </section>
  );
}
