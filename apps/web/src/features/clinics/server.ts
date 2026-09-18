import { serverFetch } from '@/lib/api/server-client';

import type { Clinic, ClinicSettings } from './api';

export async function listClinicsOnServer(): Promise<Clinic[]> {
  return serverFetch<Clinic[]>('/api/v1/clinics');
}

export async function getClinicOnServer(clinicId: string): Promise<Clinic> {
  return serverFetch<Clinic>(`/api/v1/clinics/${clinicId}`);
}

export async function getClinicSettingsOnServer(clinicId: string): Promise<ClinicSettings> {
  return serverFetch<ClinicSettings>(`/api/v1/clinics/${clinicId}/settings`);
}
