import { apiFetch, apiMutation } from '@/lib/api/client';
import type { components } from '@/lib/api/generated/schema';

export type Patient = components['schemas']['PatientResponse'];
export type PatientStatus = components['schemas']['PatientStatus'];
export type PatientList = components['schemas']['PatientListResponse'];
export type PatientCreateRequest = components['schemas']['PatientCreateRequest'];
export type PatientUpdateRequest = components['schemas']['PatientUpdateRequest'];
export type PatientAlert = components['schemas']['PatientAlertResponse'];
export type PatientAlertList = components['schemas']['PatientAlertListResponse'];
export type PatientAlertKind = components['schemas']['PatientAlertKind'];
export type PatientAlertStatus = components['schemas']['PatientAlertStatus'];
export type PatientAlertCreateRequest = components['schemas']['PatientAlertCreateRequest'];
export type PatientAlertUpdateRequest = components['schemas']['PatientAlertUpdateRequest'];

export type PatientListRequest = {
  search?: string | null;
  status?: PatientStatus;
  limit?: number;
  offset?: number;
};

function queryString(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') {
      query.set(key, String(value));
    }
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : '';
}

export async function listPatients(
  clinicId: string,
  params: PatientListRequest = {},
): Promise<PatientList> {
  return apiFetch<PatientList>(
    `/api/v1/clinics/${clinicId}/patients${queryString({
      search: params.search ?? undefined,
      status: params.status,
      limit: params.limit,
      offset: params.offset,
    })}`,
  );
}

export async function getPatient(clinicId: string, patientId: string): Promise<Patient> {
  return apiFetch<Patient>(`/api/v1/clinics/${clinicId}/patients/${patientId}`);
}

export async function createPatient(
  clinicId: string,
  payload: PatientCreateRequest,
): Promise<Patient> {
  return apiMutation<Patient>('POST', `/api/v1/clinics/${clinicId}/patients`, payload);
}

export async function updatePatient(
  clinicId: string,
  patientId: string,
  payload: PatientUpdateRequest,
): Promise<Patient> {
  return apiMutation<Patient>(
    'PATCH',
    `/api/v1/clinics/${clinicId}/patients/${patientId}`,
    payload,
  );
}

export async function archivePatient(clinicId: string, patientId: string): Promise<Patient> {
  return apiMutation<Patient>('POST', `/api/v1/clinics/${clinicId}/patients/${patientId}/archive`);
}

export async function restorePatient(clinicId: string, patientId: string): Promise<Patient> {
  return apiMutation<Patient>('POST', `/api/v1/clinics/${clinicId}/patients/${patientId}/restore`);
}

export async function listPatientAlerts(
  clinicId: string,
  patientId: string,
  params: { status?: PatientAlertStatus; limit?: number; offset?: number } = {},
): Promise<PatientAlertList> {
  return apiFetch<PatientAlertList>(
    `/api/v1/clinics/${clinicId}/patients/${patientId}/alerts${queryString({
      status: params.status,
      limit: params.limit,
      offset: params.offset,
    })}`,
  );
}

export async function createPatientAlert(
  clinicId: string,
  patientId: string,
  payload: PatientAlertCreateRequest,
): Promise<PatientAlert> {
  return apiMutation<PatientAlert>(
    'POST',
    `/api/v1/clinics/${clinicId}/patients/${patientId}/alerts`,
    payload,
  );
}

export async function updatePatientAlert(
  clinicId: string,
  patientId: string,
  alertId: string,
  payload: PatientAlertUpdateRequest,
): Promise<PatientAlert> {
  return apiMutation<PatientAlert>(
    'PATCH',
    `/api/v1/clinics/${clinicId}/patients/${patientId}/alerts/${alertId}`,
    payload,
  );
}
