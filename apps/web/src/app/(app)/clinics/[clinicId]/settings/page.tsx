import Link from 'next/link';
import { notFound } from 'next/navigation';

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
    <section className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">Configurações</h1>
        <p className="text-sm text-muted-foreground">{clinic.legal_name}</p>
      </div>
      <ClinicSettingsForm clinicId={clinic.id} role={clinic.role} initialSettings={settings} />
      <Link href={`/clinics/${clinic.id}`} className="w-fit text-sm underline">
        Voltar para a clínica
      </Link>
    </section>
  );
}
