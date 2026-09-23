import { serverFetch } from '@/lib/api/server-client';

import type { AgendaProfessional, AgendaRoom, Appointment } from './api';

async function fetchAll<T>(path: (limit: number, offset: number) => string): Promise<T[]> {
  const pageSize = 100;
  const items: T[] = [];
  let offset = 0;
  let total = 0;
  do {
    const page = await serverFetch<{ items: T[]; total: number }>(path(pageSize, offset));
    items.push(...page.items);
    total = page.total;
    offset += page.items.length;
  } while (offset < total);
  return items;
}

export async function listAgendaProfessionalsOnServer(
  clinicId: string,
  status: 'ACTIVE' | 'ARCHIVED',
): Promise<AgendaProfessional[]> {
  return fetchAll(
    (limit, offset) =>
      `/api/v1/clinics/${clinicId}/professionals?status=${status}&limit=${limit}&offset=${offset}`,
  );
}

export async function listAgendaRoomsOnServer(
  clinicId: string,
  status: 'ACTIVE' | 'ARCHIVED',
): Promise<AgendaRoom[]> {
  return fetchAll(
    (limit, offset) =>
      `/api/v1/clinics/${clinicId}/rooms?status=${status}&limit=${limit}&offset=${offset}`,
  );
}

export async function listAllAgendaResourcesOnServer(clinicId: string): Promise<{
  professionals: AgendaProfessional[];
  rooms: AgendaRoom[];
}> {
  const [activeProfessionals, archivedProfessionals, activeRooms, archivedRooms] =
    await Promise.all([
      listAgendaProfessionalsOnServer(clinicId, 'ACTIVE'),
      listAgendaProfessionalsOnServer(clinicId, 'ARCHIVED'),
      listAgendaRoomsOnServer(clinicId, 'ACTIVE'),
      listAgendaRoomsOnServer(clinicId, 'ARCHIVED'),
    ]);
  return {
    professionals: [...activeProfessionals, ...archivedProfessionals],
    rooms: [...activeRooms, ...archivedRooms],
  };
}

export async function listPatientAppointmentsOnServer(
  clinicId: string,
  patientId: string,
): Promise<Appointment[]> {
  const limit = 100;
  const items: Appointment[] = [];
  let offset = 0;
  let total = 0;
  do {
    const page = await serverFetch<{ items: Appointment[]; total: number }>(
      `/api/v1/clinics/${clinicId}/patients/${patientId}/appointments?limit=${limit}&offset=${offset}`,
    );
    items.push(...page.items);
    total = page.total;
    offset += page.items.length;
  } while (offset < total);
  return items;
}
