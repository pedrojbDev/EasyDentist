import { ClinicList } from '@/features/clinics/components/ClinicList';
import { listClinicsOnServer } from '@/features/clinics/server';

export const dynamic = 'force-dynamic';

export default async function ClinicsPage() {
  const clinics = await listClinicsOnServer();

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">Suas clínicas</h1>
        <p className="text-sm text-muted-foreground">
          Selecione a clínica com que deseja trabalhar.
        </p>
      </div>
      <ClinicList clinics={clinics} />
    </section>
  );
}
