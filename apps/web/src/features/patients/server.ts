import { serverFetch } from '@/lib/api/server-client';

import type { Patient, PatientAlertList, PatientList, PatientListRequest } from './api';

export async function listPatientsOnServer(
  clinicId: string,
  params: PatientListRequest,
): Promise<PatientList> {
  const query = new URLSearchParams();
  if (params.search) {
    query.set('search', params.search);
  }
  if (params.status) {
    query.set('status', params.status);
  }
  if (params.limit !== undefined) {
    query.set('limit', String(params.limit));
  }
  if (params.offset !== undefined) {
    query.set('offset', String(params.offset));
  }
  const serialized = query.toString();
  const suffix = serialized ? `?${serialized}` : '';
  return serverFetch<PatientList>(`/api/v1/clinics/${clinicId}/patients${suffix}`);
}

export async function getPatientOnServer(clinicId: string, patientId: string): Promise<Patient> {
  return serverFetch<Patient>(`/api/v1/clinics/${clinicId}/patients/${patientId}`);
}

export async function listPatientAlertsOnServer(
  clinicId: string,
  patientId: string,
): Promise<PatientAlertList> {
  return serverFetch<PatientAlertList>(
    `/api/v1/clinics/${clinicId}/patients/${patientId}/alerts?limit=100`,
  );
}
