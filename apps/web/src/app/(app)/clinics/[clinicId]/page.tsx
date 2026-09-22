import { notFound } from 'next/navigation';

import { PageHeader } from '@/components/ui/page-header';
import { StatusBadge } from '@/components/ui/status-badge';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { roleLabel, statusLabel } from '@/features/clinics/labels';
import { LegalNameForm } from '@/features/clinics/components/LegalNameForm';
import { getClinicOnServer } from '@/features/clinics/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function ClinicPage({ params }: { params: Promise<{ clinicId: string }> }) {
  const { clinicId } = await params;

  let clinic;
  try {
    clinic = await getClinicOnServer(clinicId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow="Visão geral da clínica"
        title={clinic.legal_name}
        description={`Identificador: ${clinic.slug}`}
      />
      <ClinicNav clinicId={clinic.id} active="overview" />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(19rem,0.65fr)]">
        <LegalNameForm
          clinicId={clinic.id}
          role={clinic.role}
          initialLegalName={clinic.legal_name}
        />
        <dl className="app-panel grid gap-5 sm:grid-cols-2 lg:grid-cols-1">
          <div>
            <dt className="text-sm font-medium text-muted-foreground">Seu papel</dt>
            <dd className="mt-2">
              <StatusBadge tone="info">{roleLabel(clinic.role)}</StatusBadge>
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-muted-foreground">Situação da clínica</dt>
            <dd className="mt-2">
              <StatusBadge tone={clinic.status === 'ACTIVE' ? 'success' : 'warning'}>
                {statusLabel(clinic.status)}
              </StatusBadge>
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
