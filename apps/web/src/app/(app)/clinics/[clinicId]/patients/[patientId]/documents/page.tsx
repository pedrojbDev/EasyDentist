import { notFound } from 'next/navigation';

import { Feedback } from '@/components/ui/feedback';
import { PageHeader } from '@/components/ui/page-header';
import { anamnesisCapabilities } from '@/features/anamnesis/permissions';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { getClinicOnServer } from '@/features/clinics/server';
import { DocumentsPanel } from '@/features/documents/components/DocumentsPanel';
import { canReadAnyDocument, documentCapabilities } from '@/features/documents/permissions';
import { listDocumentsOnServer } from '@/features/documents/server';
import { PatientSectionNav } from '@/features/patients/components/PatientSectionNav';
import { getPatientOnServer } from '@/features/patients/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function DocumentsPage({
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

  const capabilities = documentCapabilities(clinic.role);
  const canRead = canReadAnyDocument(capabilities);
  const documents = canRead ? (await listDocumentsOnServer(clinicId, patientId)).items : [];

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow={clinic.legal_name}
        title="Documentos"
        description={`Paciente: ${patient.full_name}`}
      />
      <ClinicNav clinicId={clinic.id} active="patients" />
      <PatientSectionNav
        clinicId={clinic.id}
        patientId={patient.id}
        active="documents"
        canReadAnamnesis={anamnesisCapabilities(clinic.role).canRead}
        canReadDocuments={canRead}
      />

      {canRead ? (
        <DocumentsPanel
          clinicId={clinic.id}
          patientId={patient.id}
          documents={documents}
          capabilities={capabilities}
        />
      ) : (
        <div className="app-panel">
          <Feedback tone="error">
            Seu papel nesta clínica não permite visualizar documentos.
          </Feedback>
        </div>
      )}
    </section>
  );
}
