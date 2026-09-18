import { ClinicList } from '@/features/clinics/components/ClinicList';
import { listClinicsOnServer } from '@/features/clinics/server';

export const dynamic = 'force-dynamic';

export default async function ClinicsPage() {
  const clinics = await listClinicsOnServer();

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
import { PageHeader } from '@/components/ui/page-header';
