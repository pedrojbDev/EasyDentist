import { serverFetch } from '@/lib/api/server-client';

import type { Member } from './api';

export async function listMembersOnServer(clinicId: string): Promise<Member[]> {
  return serverFetch<Member[]>(`/api/v1/clinics/${clinicId}/memberships`);
}
