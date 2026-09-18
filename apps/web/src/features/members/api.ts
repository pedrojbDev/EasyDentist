import { apiFetch, apiMutation, apiMutationVoid } from '@/lib/api/client';
import type { components } from '@/lib/api/generated/schema';

export type Member = components['schemas']['MembershipResponse'];
export type Role = components['schemas']['Role'];

export async function listMembers(clinicId: string): Promise<Member[]> {
  return apiFetch<Member[]>(`/api/v1/clinics/${clinicId}/memberships`);
}

export async function changeRole(
  clinicId: string,
  membershipId: string,
  role: Role,
): Promise<Member> {
  return apiMutation<Member>('PATCH', `/api/v1/clinics/${clinicId}/memberships/${membershipId}`, {
    role,
  });
}

export async function removeMember(clinicId: string, membershipId: string): Promise<void> {
  await apiMutationVoid('DELETE', `/api/v1/clinics/${clinicId}/memberships/${membershipId}`);
}

export async function inviteMember(
  clinicId: string,
  email: string,
  role: Role,
): Promise<components['schemas']['MembershipInvitationResponse']> {
  return apiMutation('POST', `/api/v1/clinics/${clinicId}/invitations`, { email, role });
}
