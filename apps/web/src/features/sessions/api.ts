import { apiFetch, apiMutationVoid } from '@/lib/api/client';
import type { components } from '@/lib/api/generated/schema';

export type Session = components['schemas']['SessionResponse'];

export async function listSessions(): Promise<Session[]> {
  return apiFetch<Session[]>('/api/v1/auth/sessions');
}

export async function revokeSession(sessionId: string): Promise<void> {
  await apiMutationVoid('DELETE', `/api/v1/auth/sessions/${sessionId}`);
}
