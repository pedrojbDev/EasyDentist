import { notFound } from 'next/navigation';

import { PageHeader } from '@/components/ui/page-header';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { ClinicSettingsForm } from '@/features/clinics/components/ClinicSettingsForm';
import { getClinicOnServer, getClinicSettingsOnServer } from '@/features/clinics/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function ClinicSettingsPage({
  params,
}: {
  params: Promise<{ clinicId: string }>;
}) {
  const { clinicId } = await params;

  let clinic;
  let settings;
  try {
    [clinic, settings] = await Promise.all([
      getClinicOnServer(clinicId),
      getClinicSettingsOnServer(clinicId),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow={clinic.legal_name}
        title="Ajustes da clínica"
        description="Informações usadas na operação e apresentação da clínica."
      />
      <ClinicNav clinicId={clinic.id} active="settings" />
      <ClinicSettingsForm clinicId={clinic.id} role={clinic.role} initialSettings={settings} />
    </section>
  );
}
