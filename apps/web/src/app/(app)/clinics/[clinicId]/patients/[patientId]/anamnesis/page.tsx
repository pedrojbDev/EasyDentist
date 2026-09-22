import { notFound } from 'next/navigation';

import { Feedback } from '@/components/ui/feedback';
import { PageHeader } from '@/components/ui/page-header';
import { AnamnesisForm } from '@/features/anamnesis/components/AnamnesisForm';
import { AnamnesisHistory } from '@/features/anamnesis/components/AnamnesisHistory';
import { AnamnesisReadOnly } from '@/features/anamnesis/components/AnamnesisReadOnly';
import { AnamnesisRestricted } from '@/features/anamnesis/components/AnamnesisRestricted';
import { AnamnesisStartActions } from '@/features/anamnesis/components/AnamnesisStartActions';
import { anamnesisCapabilities } from '@/features/anamnesis/permissions';
import { getProfessionalProfileOnServer, listAnamnesesOnServer } from '@/features/anamnesis/server';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { getClinicOnServer } from '@/features/clinics/server';
import { canReadAnyDocument, documentCapabilities } from '@/features/documents/permissions';
import { PatientSectionNav } from '@/features/patients/components/PatientSectionNav';
import { getPatientOnServer } from '@/features/patients/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function AnamnesisPage({
  params,
}: {
  params: Promise<{ clinicId: string; patientId: string }>;
}) {
  const { clinicId, patientId } = await params;

  let clinic;
  let patient;
  try {
    clinic = await getClinicOnServer(clinicId);
    patient = await getPatientOnServer(clinicId, patientId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  const capabilities = anamnesisCapabilities(clinic.role);
  const versions = capabilities.canRead
    ? (await listAnamnesesOnServer(clinicId, patientId)).items
    : [];
  const profile = capabilities.canFinalize ? await getProfessionalProfileOnServer() : null;
  const draft = versions.find((version) => version.status === 'DRAFT') ?? null;

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow={clinic.legal_name}
        title="Anamnese"
        description={`Paciente: ${patient.full_name}`}
      />
      <ClinicNav clinicId={clinic.id} active="patients" />
      <PatientSectionNav
        clinicId={clinic.id}
        patientId={patient.id}
        active="anamnesis"
        canReadAnamnesis={capabilities.canRead}
        canReadDocuments={canReadAnyDocument(documentCapabilities(clinic.role))}
      />

      {!capabilities.canRead ? (
        <AnamnesisRestricted />
      ) : (
        <>
          {draft === null ? (
            capabilities.canCreate && (
              <AnamnesisStartActions
                clinicId={clinic.id}
                patientId={patient.id}
                latestFinal={
                  versions
                    .filter((version) => version.status === 'FINAL')
                    .sort(
                      (left, right) => (right.version_number ?? 0) - (left.version_number ?? 0),
                    )[0] ?? null
                }
              />
            )
          ) : capabilities.canUpdate ? (
            <AnamnesisForm
              clinicId={clinic.id}
              patientId={patient.id}
              anamnesis={draft}
              profile={profile}
              patientName={patient.full_name}
              canFinalize={capabilities.canFinalize}
            />
          ) : (
            <>
              <Feedback tone="info">
                Seu papel permite apenas leitura. O rascunho em andamento não pode ser alterado por
                você.
              </Feedback>
              <AnamnesisReadOnly anamnesis={draft} />
            </>
          )}

          <AnamnesisHistory clinicId={clinic.id} patientId={patient.id} versions={versions} />
        </>
      )}
    </section>
  );
}
