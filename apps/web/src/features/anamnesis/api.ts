import { apiFetch, apiMutation } from '@/lib/api/client';
import type { components } from '@/lib/api/generated/schema';

export type Anamnesis = components['schemas']['AnamnesisResponse'];
export type AnamnesisStatus = components['schemas']['AnamnesisStatus'];
export type AnamnesisList = components['schemas']['AnamnesisListResponse'];
export type AnamnesisPayload = components['schemas']['AnamnesisPayload'];
export type ProfessionalProfile = components['schemas']['ProfessionalProfileResponse'];
export type ProfessionalProfileRequest = components['schemas']['ProfessionalProfileRequest'];

export type AnamnesisListRequest = {
  status?: AnamnesisStatus;
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

export async function listAnamneses(
  clinicId: string,
  patientId: string,
  params: AnamnesisListRequest = {},
): Promise<AnamnesisList> {
  return apiFetch<AnamnesisList>(
    `/api/v1/clinics/${clinicId}/patients/${patientId}/anamneses${queryString({
      status: params.status,
      limit: params.limit,
      offset: params.offset,
    })}`,
  );
}

export async function getAnamnesis(
  clinicId: string,
  patientId: string,
  anamnesisId: string,
): Promise<Anamnesis> {
  return apiFetch<Anamnesis>(
    `/api/v1/clinics/${clinicId}/patients/${patientId}/anamneses/${anamnesisId}`,
  );
}

export async function createAnamnesis(
  clinicId: string,
  patientId: string,
  payload: { base_version_id?: string | null } = {},
): Promise<Anamnesis> {
  return apiMutation<Anamnesis>(
    'POST',
    `/api/v1/clinics/${clinicId}/patients/${patientId}/anamneses`,
    payload,
  );
}

export async function updateAnamnesis(
  clinicId: string,
  patientId: string,
  anamnesisId: string,
  payload: AnamnesisPayload,
): Promise<Anamnesis> {
  return apiMutation<Anamnesis>(
    'PATCH',
    `/api/v1/clinics/${clinicId}/patients/${patientId}/anamneses/${anamnesisId}`,
    { payload },
  );
}

export async function finalizeAnamnesis(
  clinicId: string,
  patientId: string,
  anamnesisId: string,
): Promise<Anamnesis> {
  return apiMutation<Anamnesis>(
    'POST',
    `/api/v1/clinics/${clinicId}/patients/${patientId}/anamneses/${anamnesisId}/finalize`,
  );
}

export async function getProfessionalProfile(): Promise<ProfessionalProfile | null> {
  return apiFetch<ProfessionalProfile | null>('/api/v1/users/me/professional-profile');
}

export async function saveProfessionalProfile(
  payload: ProfessionalProfileRequest,
): Promise<ProfessionalProfile> {
  return apiMutation<ProfessionalProfile>('PUT', '/api/v1/users/me/professional-profile', payload);
}
