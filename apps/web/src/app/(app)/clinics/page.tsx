import { redirect } from 'next/navigation';

import { PageHeader } from '@/components/ui/page-header';
import { ClinicList } from '@/features/clinics/components/ClinicList';
import { listClinicsOnServer } from '@/features/clinics/server';

export const dynamic = 'force-dynamic';

export default async function ClinicsPage() {
  const clinics = await listClinicsOnServer();
  if (clinics.length === 1 && clinics[0].status === 'ACTIVE') {
    redirect(`/clinics/${clinics[0].id}/agenda`);
  }

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow="Área de trabalho"
        title="Suas clínicas"
        description="Escolha a clínica em que deseja trabalhar agora."
      />
      <ClinicList clinics={clinics} />
    </section>
  );
}
