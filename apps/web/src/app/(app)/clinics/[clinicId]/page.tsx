import Link from 'next/link';
import { notFound } from 'next/navigation';

import { roleLabel, statusLabel } from '@/features/clinics/components/ClinicList';
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
    <section className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">{clinic.legal_name}</h1>
        <p className="text-sm text-muted-foreground">{clinic.slug}</p>
      </div>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Papel</dt>
          <dd>{roleLabel(clinic.role)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Situação</dt>
          <dd>{statusLabel(clinic.status)}</dd>
        </div>
      </dl>
      <LegalNameForm clinicId={clinic.id} role={clinic.role} initialLegalName={clinic.legal_name} />
      <div className="flex gap-4 text-sm">
        <Link href={`/clinics/${clinic.id}/settings`} className="underline">
          Configurações da clínica
        </Link>
        <Link href={`/clinics/${clinic.id}/members`} className="underline">
          Equipe e convites
        </Link>
      </div>
    </section>
  );
}
