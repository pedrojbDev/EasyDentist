import { serverFetch } from '@/lib/api/server-client';

import type { Session } from './api';

export async function listSessionsOnServer(): Promise<Session[]> {
  return serverFetch<Session[]>('/api/v1/auth/sessions');
}
