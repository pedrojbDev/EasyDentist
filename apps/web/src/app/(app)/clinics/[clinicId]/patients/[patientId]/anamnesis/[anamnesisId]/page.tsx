import { ArrowLeft } from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { AnamnesisReadOnly } from '@/features/anamnesis/components/AnamnesisReadOnly';
import { AnamnesisRestricted } from '@/features/anamnesis/components/AnamnesisRestricted';
import { AnamnesisRevisionButton } from '@/features/anamnesis/components/AnamnesisStartActions';
import { anamnesisCapabilities } from '@/features/anamnesis/permissions';
import { getAnamnesisOnServer, listAnamnesesOnServer } from '@/features/anamnesis/server';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { getClinicOnServer } from '@/features/clinics/server';
import { canReadAnyDocument, documentCapabilities } from '@/features/documents/permissions';
import { PatientSectionNav } from '@/features/patients/components/PatientSectionNav';
import { getPatientOnServer } from '@/features/patients/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function AnamnesisVersionPage({
  params,
}: {
  params: Promise<{ clinicId: string; patientId: string; anamnesisId: string }>;
}) {
  const { clinicId, patientId, anamnesisId } = await params;

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
  const mainPath = `/clinics/${clinic.id}/patients/${patient.id}/anamnesis`;

  if (!capabilities.canRead) {
    return (
      <section className="flex flex-col gap-7">
        <PageHeader eyebrow={clinic.legal_name} title="Anamnese" />
        <ClinicNav clinicId={clinic.id} active="patients" />
        <PatientSectionNav
          clinicId={clinic.id}
          patientId={patient.id}
          active="anamnesis"
          canReadAnamnesis={false}
          canReadDocuments={canReadAnyDocument(documentCapabilities(clinic.role))}
        />
        <AnamnesisRestricted />
      </section>
    );
  }

  const versions = (await listAnamnesesOnServer(clinicId, patientId)).items;
  let anamnesis;
  try {
    anamnesis = await getAnamnesisOnServer(clinicId, patientId, anamnesisId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
  if (anamnesis.status === 'DRAFT') {
    redirect(mainPath as Route);
  }

  const latestFinal = versions
    .filter((version) => version.status === 'FINAL')
    .sort((left, right) => (right.version_number ?? 0) - (left.version_number ?? 0))[0];
  const hasDraft = versions.some((version) => version.status === 'DRAFT');
  const canRevise = capabilities.canCreate && !hasDraft && latestFinal?.id === anamnesis.id;

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow={clinic.legal_name}
        title={`Anamnese — versão ${anamnesis.version_number ?? '—'}`}
        description={`Paciente: ${patient.full_name}`}
        actions={
          <Button asChild variant="outline">
            <Link href={mainPath as Route}>
              <ArrowLeft aria-hidden="true" />
              Voltar
            </Link>
          </Button>
        }
      />
      <ClinicNav clinicId={clinic.id} active="patients" />
      <PatientSectionNav
        clinicId={clinic.id}
        patientId={patient.id}
        active="anamnesis"
        canReadAnamnesis={true}
        canReadDocuments={canReadAnyDocument(documentCapabilities(clinic.role))}
      />

      <AnamnesisReadOnly anamnesis={anamnesis} />

      {canRevise && (
        <section className="app-panel flex flex-col gap-3" aria-labelledby="anamnesis-revise-title">
          <h2 id="anamnesis-revise-title" className="font-semibold text-foreground">
            Nova revisão
          </h2>
          <p className="text-sm text-muted-foreground">
            Inicie um rascunho copiando as respostas desta versão. Ao concluir, ele passa a ser a
            versão vigente.
          </p>
          <AnamnesisRevisionButton
            clinicId={clinic.id}
            patientId={patient.id}
            baseVersionId={anamnesis.id}
          />
        </section>
      )}
    </section>
  );
}
