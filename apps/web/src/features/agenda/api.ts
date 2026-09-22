import { apiFetch, apiMutation } from '@/lib/api/client';
import type { components } from '@/lib/api/generated/schema';

export type AgendaProfessional = components['schemas']['AgendaProfessionalResponse'];
export type AgendaRoom = components['schemas']['AgendaRoomResponse'];
export type AgendaProfessionalList = components['schemas']['AgendaProfessionalListResponse'];
export type AgendaRoomList = components['schemas']['AgendaRoomListResponse'];
export type AgendaProfessionalCreateRequest =
  components['schemas']['AgendaProfessionalCreateRequest'];
export type AgendaProfessionalUpdateRequest =
  components['schemas']['AgendaProfessionalUpdateRequest'];
export type AgendaRoomCreateRequest = components['schemas']['AgendaRoomCreateRequest'];
export type AgendaRoomUpdateRequest = components['schemas']['AgendaRoomUpdateRequest'];
export type Appointment = components['schemas']['AppointmentResponse'];
export type AppointmentStatus = components['schemas']['AppointmentStatus'];
export type AppointmentCreateRequest = components['schemas']['AppointmentCreateRequest'];
export type AppointmentUpdateRequest = components['schemas']['AppointmentUpdateRequest'];
export type AppointmentRescheduleRequest = components['schemas']['AppointmentRescheduleRequest'];
export type AppointmentStatusRequest = components['schemas']['AppointmentStatusRequest'];
export type AppointmentHistoryList = components['schemas']['AppointmentHistoryListResponse'];
export type ScheduleBlock = components['schemas']['ScheduleBlockResponse'];
export type ScheduleBlockCreateRequest = components['schemas']['ScheduleBlockCreateRequest'];
export type ScheduleBlockUpdateRequest = components['schemas']['ScheduleBlockUpdateRequest'];
export type ScheduleBlockCancelRequest = components['schemas']['ScheduleBlockCancelRequest'];
export type WorkingHourInterval = components['schemas']['WorkingHourInterval'];
export type WorkingHours = components['schemas']['WorkingHoursResponse'];
export type WorkingHoursReplaceRequest = components['schemas']['WorkingHoursReplaceRequest'];
export type Availability = components['schemas']['AvailabilityResponse'];

export type AgendaRange = {
  starts_at: string;
  ends_at: string;
  professional_id?: string;
  room_id?: string;
  patient_id?: string;
  status?: AppointmentStatus;
  limit?: number;
  offset?: number;
};

function queryString(params: { status?: string; limit?: number; offset?: number }): string {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.offset !== undefined) query.set('offset', String(params.offset));
  const value = query.toString();
  return value ? `?${value}` : '';
}

export async function listProfessionals(
  clinicId: string,
  params: { status?: 'ACTIVE' | 'ARCHIVED'; limit?: number; offset?: number } = {},
): Promise<AgendaProfessionalList> {
  return apiFetch(`/api/v1/clinics/${clinicId}/professionals${queryString(params)}`);
}

export async function createProfessional(
  clinicId: string,
  payload: AgendaProfessionalCreateRequest,
): Promise<AgendaProfessional> {
  return apiMutation('POST', `/api/v1/clinics/${clinicId}/professionals`, payload);
}

export async function updateProfessional(
  clinicId: string,
  id: string,
  payload: AgendaProfessionalUpdateRequest,
): Promise<AgendaProfessional> {
  return apiMutation('PATCH', `/api/v1/clinics/${clinicId}/professionals/${id}`, payload);
}

export async function setProfessionalArchived(
  clinicId: string,
  id: string,
  archived: boolean,
): Promise<AgendaProfessional> {
  return apiMutation(
    'POST',
    `/api/v1/clinics/${clinicId}/professionals/${id}/${archived ? 'archive' : 'restore'}`,
  );
}

export async function listRooms(
  clinicId: string,
  params: { status?: 'ACTIVE' | 'ARCHIVED'; limit?: number; offset?: number } = {},
): Promise<AgendaRoomList> {
  return apiFetch(`/api/v1/clinics/${clinicId}/rooms${queryString(params)}`);
}

export async function createRoom(
  clinicId: string,
  payload: AgendaRoomCreateRequest,
): Promise<AgendaRoom> {
  return apiMutation('POST', `/api/v1/clinics/${clinicId}/rooms`, payload);
}

export async function updateRoom(
  clinicId: string,
  id: string,
  payload: AgendaRoomUpdateRequest,
): Promise<AgendaRoom> {
  return apiMutation('PATCH', `/api/v1/clinics/${clinicId}/rooms/${id}`, payload);
}

export async function setRoomArchived(
  clinicId: string,
  id: string,
  archived: boolean,
): Promise<AgendaRoom> {
  return apiMutation(
    'POST',
    `/api/v1/clinics/${clinicId}/rooms/${id}/${archived ? 'archive' : 'restore'}`,
  );
}

function agendaQuery(params: Record<string, string | number | boolean | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value));
  }
  return query.size ? `?${query.toString()}` : '';
}

export async function listAppointments(
  clinicId: string,
  params: AgendaRange,
): Promise<components['schemas']['AppointmentListResponse']> {
  return apiFetch(`/api/v1/clinics/${clinicId}/appointments${agendaQuery(params)}`);
}

export async function listAllAppointments(
  clinicId: string,
  params: Omit<AgendaRange, 'limit' | 'offset'>,
): Promise<Appointment[]> {
  const limit = 100;
  const items: Appointment[] = [];
  let offset = 0;
  let total = 0;
  do {
    const page = await listAppointments(clinicId, { ...params, limit, offset });
    items.push(...page.items);
    total = page.total;
    offset += page.items.length;
  } while (offset < total);
  return items;
}

export async function createAppointment(
  clinicId: string,
  payload: AppointmentCreateRequest,
): Promise<Appointment> {
  return apiMutation('POST', `/api/v1/clinics/${clinicId}/appointments`, payload);
}

export async function updateAppointment(
  clinicId: string,
  id: string,
  payload: AppointmentUpdateRequest,
): Promise<Appointment> {
  return apiMutation('PATCH', `/api/v1/clinics/${clinicId}/appointments/${id}`, payload);
}

export async function rescheduleAppointment(
  clinicId: string,
  id: string,
  payload: AppointmentRescheduleRequest,
): Promise<Appointment> {
  return apiMutation('POST', `/api/v1/clinics/${clinicId}/appointments/${id}/reschedule`, payload);
}

export async function setAppointmentStatus(
  clinicId: string,
  id: string,
  payload: AppointmentStatusRequest,
): Promise<Appointment> {
  return apiMutation('POST', `/api/v1/clinics/${clinicId}/appointments/${id}/status`, payload);
}

export async function listAppointmentHistory(
  clinicId: string,
  id: string,
): Promise<AppointmentHistoryList> {
  return apiFetch(`/api/v1/clinics/${clinicId}/appointments/${id}/history?limit=100`);
}

export async function listPatientAppointments(
  clinicId: string,
  patientId: string,
): Promise<components['schemas']['AppointmentListResponse']> {
  return apiFetch(`/api/v1/clinics/${clinicId}/patients/${patientId}/appointments?limit=100`);
}

export async function listScheduleBlocks(
  clinicId: string,
  params: Omit<AgendaRange, 'patient_id' | 'status'> & { include_cancelled?: boolean },
): Promise<components['schemas']['ScheduleBlockListResponse']> {
  return apiFetch(`/api/v1/clinics/${clinicId}/schedule-blocks${agendaQuery(params)}`);
}

export async function createScheduleBlock(
  clinicId: string,
  payload: ScheduleBlockCreateRequest,
): Promise<ScheduleBlock> {
  return apiMutation('POST', `/api/v1/clinics/${clinicId}/schedule-blocks`, payload);
}

export async function updateScheduleBlock(
  clinicId: string,
  id: string,
  payload: ScheduleBlockUpdateRequest,
): Promise<ScheduleBlock> {
  return apiMutation('PATCH', `/api/v1/clinics/${clinicId}/schedule-blocks/${id}`, payload);
}

export async function cancelScheduleBlock(
  clinicId: string,
  id: string,
  payload: ScheduleBlockCancelRequest = {},
): Promise<ScheduleBlock> {
  return apiMutation('POST', `/api/v1/clinics/${clinicId}/schedule-blocks/${id}/cancel`, payload);
}

export async function getWorkingHours(
  clinicId: string,
  professionalId: string,
): Promise<WorkingHours> {
  return apiFetch(`/api/v1/clinics/${clinicId}/professionals/${professionalId}/working-hours`);
}

export async function replaceWorkingHours(
  clinicId: string,
  professionalId: string,
  payload: WorkingHoursReplaceRequest,
): Promise<WorkingHours> {
  return apiMutation(
    'PUT',
    `/api/v1/clinics/${clinicId}/professionals/${professionalId}/working-hours`,
    payload,
  );
}

export async function findAvailability(
  clinicId: string,
  params: {
    professional_id: string;
    local_date: string;
    duration_minutes?: number;
    patient_id?: string;
    room_id?: string;
    step_minutes?: number;
  },
): Promise<Availability> {
  return apiFetch(`/api/v1/clinics/${clinicId}/availability${agendaQuery(params)}`);
}
