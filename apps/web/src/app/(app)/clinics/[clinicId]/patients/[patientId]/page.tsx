import { Pencil } from 'lucide-react';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { StatusBadge } from '@/components/ui/status-badge';
import { anamnesisCapabilities } from '@/features/anamnesis/permissions';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { getClinicOnServer } from '@/features/clinics/server';
import { formatCpf } from '@/features/patients/cpf';
import { PatientAlertsPanel } from '@/features/patients/components/PatientAlertsPanel';
import { PatientArchiveButton } from '@/features/patients/components/PatientArchiveButton';
import { PatientDetails } from '@/features/patients/components/PatientDetails';
import { PatientSectionNav } from '@/features/patients/components/PatientSectionNav';
import { formatDate, patientStatusLabel } from '@/features/patients/labels';
import { patientCapabilities } from '@/features/patients/permissions';
import { getPatientOnServer, listPatientAlertsOnServer } from '@/features/patients/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function PatientDetailPage({
  params,
}: {
  params: Promise<{ clinicId: string; patientId: string }>;
}) {
  const { clinicId, patientId } = await params;

  let clinic;
  let patient;
  let alerts;
  try {
    clinic = await getClinicOnServer(clinicId);
    patient = await getPatientOnServer(clinicId, patientId);
    alerts = patientCapabilities(clinic.role).canReadAlerts
      ? (await listPatientAlertsOnServer(clinicId, patientId)).items
      : [];
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  const capabilities = patientCapabilities(clinic.role);
  const subtitle = [
    patient.social_name ? `Nome social: ${patient.social_name}` : null,
    patient.cpf ? `CPF ${formatCpf(patient.cpf)}` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow={clinic.legal_name}
        title={patient.full_name}
        description={subtitle || undefined}
        actions={
          <>
            {capabilities.canUpdate && (
              <Button asChild variant="outline">
                <Link href={`/clinics/${clinic.id}/patients/${patient.id}/edit`}>
                  <Pencil aria-hidden="true" />
                  Editar
                </Link>
              </Button>
            )}
            {capabilities.canArchive && (
              <PatientArchiveButton
                clinicId={clinic.id}
                patientId={patient.id}
                patientName={patient.full_name}
                archived={patient.status === 'ARCHIVED'}
              />
            )}
          </>
        }
      />
      <ClinicNav clinicId={clinic.id} active="patients" />
      <PatientSectionNav
        clinicId={clinic.id}
        patientId={patient.id}
        active="record"
        canReadAnamnesis={anamnesisCapabilities(clinic.role).canRead}
      />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(19rem,0.6fr)]">
        <PatientDetails patient={patient} />
        <div className="flex flex-col gap-5">
          <dl className="app-panel flex flex-col gap-4">
            <div>
              <dt className="text-sm font-medium text-muted-foreground">Situação</dt>
              <dd className="mt-2">
                <StatusBadge tone={patient.status === 'ACTIVE' ? 'success' : 'neutral'}>
                  {patientStatusLabel(patient.status)}
                </StatusBadge>
              </dd>
            </div>
            {patient.archived_at !== null && (
              <div>
                <dt className="text-sm font-medium text-muted-foreground">Arquivado em</dt>
                <dd className="mt-1 text-sm text-foreground">{formatDate(patient.archived_at)}</dd>
              </div>
            )}
            <div>
              <dt className="text-sm font-medium text-muted-foreground">Cadastrado em</dt>
              <dd className="mt-1 text-sm text-foreground">{formatDate(patient.created_at)}</dd>
            </div>
          </dl>
          {capabilities.canReadAlerts && (
            <PatientAlertsPanel
              clinicId={clinic.id}
              patientId={patient.id}
              alerts={alerts}
              canManage={capabilities.canManageAlerts}
            />
          )}
        </div>
      </div>
    </section>
  );
}
