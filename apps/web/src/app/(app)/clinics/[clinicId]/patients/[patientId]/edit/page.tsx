import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Feedback } from '@/components/ui/feedback';
import { PageHeader } from '@/components/ui/page-header';
import { anamnesisCapabilities } from '@/features/anamnesis/permissions';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { getClinicOnServer } from '@/features/clinics/server';
import { canReadAnyDocument, documentCapabilities } from '@/features/documents/permissions';
import { PatientForm } from '@/features/patients/components/PatientForm';
import { PatientSectionNav } from '@/features/patients/components/PatientSectionNav';
import { patientCapabilities } from '@/features/patients/permissions';
import { getPatientOnServer } from '@/features/patients/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function EditPatientPage({
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

  const capabilities = patientCapabilities(clinic.role);

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow={clinic.legal_name}
        title={`Editar ${patient.full_name}`}
        description="Atualize os dados cadastrais. Alterações ficam registradas na auditoria da clínica."
      />
      <ClinicNav clinicId={clinic.id} active="patients" />
      <PatientSectionNav
        clinicId={clinic.id}
        patientId={patient.id}
        active="record"
        canReadAnamnesis={anamnesisCapabilities(clinic.role).canRead}
        canReadDocuments={canReadAnyDocument(documentCapabilities(clinic.role))}
      />
      {capabilities.canUpdate ? (
        <PatientForm clinicId={clinic.id} mode="edit" patient={patient} />
      ) : (
        <div className="app-panel flex flex-col gap-3">
          <Feedback tone="error">Seu papel nesta clínica não permite editar pacientes.</Feedback>
          <Link
            href={`/clinics/${clinic.id}/patients/${patient.id}`}
            className="app-link w-fit text-sm"
          >
            Voltar para os dados do paciente
          </Link>
        </div>
      )}
    </section>
  );
}
