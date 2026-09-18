import { notFound } from 'next/navigation';

import { PageHeader } from '@/components/ui/page-header';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { getClinicOnServer } from '@/features/clinics/server';
import { InviteMemberForm } from '@/features/members/components/InviteMemberForm';
import { MembersTable } from '@/features/members/components/MembersTable';
import { listMembersOnServer } from '@/features/members/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function MembersPage({ params }: { params: Promise<{ clinicId: string }> }) {
  const { clinicId } = await params;

  let clinic;
  let members;
  try {
    [clinic, members] = await Promise.all([
      getClinicOnServer(clinicId),
      listMembersOnServer(clinicId),
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
        title="Equipe"
        description="Gerencie os vínculos, papéis e convites desta clínica."
      />
      <ClinicNav clinicId={clinic.id} active="members" />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <MembersTable clinicId={clinic.id} actorRole={clinic.role} members={members} />
        <InviteMemberForm clinicId={clinic.id} actorRole={clinic.role} />
      </div>
    </section>
  );
}
