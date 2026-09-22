import { serverFetch } from '@/lib/api/server-client';

import type { Anamnesis, AnamnesisList, ProfessionalProfile } from './api';

export async function listAnamnesesOnServer(
  clinicId: string,
  patientId: string,
): Promise<AnamnesisList> {
  return serverFetch<AnamnesisList>(
    `/api/v1/clinics/${clinicId}/patients/${patientId}/anamneses?limit=100`,
  );
}

export async function getAnamnesisOnServer(
  clinicId: string,
  patientId: string,
  anamnesisId: string,
): Promise<Anamnesis> {
  return serverFetch<Anamnesis>(
    `/api/v1/clinics/${clinicId}/patients/${patientId}/anamneses/${anamnesisId}`,
  );
}

export async function getProfessionalProfileOnServer(): Promise<ProfessionalProfile | null> {
  return serverFetch<ProfessionalProfile | null>('/api/v1/users/me/professional-profile');
}
