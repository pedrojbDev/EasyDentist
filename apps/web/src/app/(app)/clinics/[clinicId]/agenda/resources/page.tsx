import { notFound } from 'next/navigation';

import { PageHeader } from '@/components/ui/page-header';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { getClinicOnServer } from '@/features/clinics/server';
import { listMembersOnServer } from '@/features/members/server';
import { getCurrentUser } from '@/features/auth/server';
import { ApiError } from '@/lib/api/problem';

import { AgendaResourceManager } from '@/features/agenda/components/AgendaResourceManager';
import { listAllAgendaResourcesOnServer } from '@/features/agenda/server';

export const dynamic = 'force-dynamic';

export default async function AgendaResourcesPage({
  params,
}: {
  params: Promise<{ clinicId: string }>;
}) {
  const { clinicId } = await params;
  let clinic;
  let resources;
  let members;
  let user;
  try {
    [clinic, resources, members, user] = await Promise.all([
      getClinicOnServer(clinicId),
      listAllAgendaResourcesOnServer(clinicId),
      listMembersOnServer(clinicId),
      getCurrentUser(),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow={clinic.legal_name}
        title="Profissionais e salas"
        description="Cadastre quem atende e os recursos físicos usados pela agenda."
      />
      <ClinicNav clinicId={clinic.id} active="agenda-resources" />
      <AgendaResourceManager
        clinicId={clinic.id}
        role={clinic.role}
        currentUserId={user.id}
        initialProfessionals={resources.professionals}
        initialRooms={resources.rooms}
        members={members}
      />
    </section>
  );
}
