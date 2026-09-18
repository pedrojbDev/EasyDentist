import { apiFetch, apiMutation } from '@/lib/api/client';
import type { components } from '@/lib/api/generated/schema';

export type Clinic = components['schemas']['ClinicResponse'];
export type ClinicSettings = components['schemas']['ClinicSettingsResponse'];
export type ClinicSettingsUpdateRequest = components['schemas']['ClinicSettingsUpdateRequest'];

export async function listClinics(): Promise<Clinic[]> {
  return apiFetch<Clinic[]>('/api/v1/clinics');
}

export async function updateClinic(clinicId: string, legalName: string): Promise<Clinic> {
  return apiMutation<Clinic>('PATCH', `/api/v1/clinics/${clinicId}`, {
    legal_name: legalName,
  });
}

export async function getSettings(clinicId: string): Promise<ClinicSettings> {
  return apiFetch<ClinicSettings>(`/api/v1/clinics/${clinicId}/settings`);
}

export async function updateSettings(
  clinicId: string,
  payload: ClinicSettingsUpdateRequest,
): Promise<ClinicSettings> {
  return apiMutation<ClinicSettings>('PATCH', `/api/v1/clinics/${clinicId}/settings`, payload);
}
