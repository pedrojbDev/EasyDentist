import Link from 'next/link';
import { notFound } from 'next/navigation';

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
    <section className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">Equipe</h1>
        <p className="text-sm text-muted-foreground">{clinic.legal_name}</p>
      </div>
      <InviteMemberForm clinicId={clinic.id} actorRole={clinic.role} />
      <MembersTable clinicId={clinic.id} actorRole={clinic.role} members={members} />
      <Link href={`/clinics/${clinic.id}`} className="w-fit text-sm underline">
        Voltar para a clínica
      </Link>
    </section>
  );
}
