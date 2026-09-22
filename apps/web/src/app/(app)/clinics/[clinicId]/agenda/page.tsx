import { notFound } from 'next/navigation';

import { PageHeader } from '@/components/ui/page-header';
import { getCurrentUser } from '@/features/auth/server';
import { ClinicNav } from '@/features/clinics/components/ClinicNav';
import { getClinicOnServer, getClinicSettingsOnServer } from '@/features/clinics/server';
import { listMembersOnServer } from '@/features/members/server';
import { ApiError } from '@/lib/api/problem';

import { AgendaCalendar } from '@/features/agenda/components/AgendaCalendar';
import { listAgendaProfessionalsOnServer, listAgendaRoomsOnServer } from '@/features/agenda/server';

export const dynamic = 'force-dynamic';

export default async function AgendaPage({
  params,
}: {
  params: Promise<{ clinicId: string }>;
}) {
  const { clinicId } = await params;
  let clinic;
  let settings;
  let professionals;
  let rooms;
  let members;
  let user;
  try {
    [clinic, settings, professionals, rooms, members, user] = await Promise.all([
      getClinicOnServer(clinicId),
      getClinicSettingsOnServer(clinicId),
      listAgendaProfessionalsOnServer(clinicId, 'ACTIVE'),
      listAgendaRoomsOnServer(clinicId, 'ACTIVE'),
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
        title="Agenda clínica"
        description={`Consultas e bloqueios no fuso ${settings.timezone}.`}
      />
      <ClinicNav clinicId={clinic.id} active="agenda" />
      <AgendaCalendar
        clinicId={clinic.id}
        clinicPath={`/clinics/${clinic.id}`}
        timezone={settings.timezone}
        role={clinic.role}
        currentUserId={user.id}
        professionals={professionals}
        rooms={rooms}
        members={members}
      />
    </section>
  );
}
