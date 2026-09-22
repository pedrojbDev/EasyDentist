import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Feedback } from '@/components/ui/feedback';
import { PageHeader } from '@/components/ui/page-header';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { getClinicOnServer } from '@/features/clinics/server';
import { PatientForm } from '@/features/patients/components/PatientForm';
import { patientCapabilities } from '@/features/patients/permissions';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function NewPatientPage({
  params,
}: {
  params: Promise<{ clinicId: string }>;
}) {
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

  const capabilities = patientCapabilities(clinic.role);

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow={clinic.legal_name}
        title="Novo paciente"
        description="Preencha os dados cadastrais. Nome, nascimento e telefone são obrigatórios."
      />
      <ClinicNav clinicId={clinic.id} active="patients" />
      {capabilities.canCreate ? (
        <PatientForm clinicId={clinic.id} mode="create" />
      ) : (
        <div className="app-panel flex flex-col gap-3">
          <Feedback tone="error">Seu papel nesta clínica não permite cadastrar pacientes.</Feedback>
          <Link href={`/clinics/${clinic.id}/patients`} className="app-link w-fit text-sm">
            Voltar para a lista de pacientes
          </Link>
        </div>
      )}
    </section>
  );
}
