import { serverFetch } from '@/lib/api/server-client';

import type { User } from './api';

export async function getCurrentUser(): Promise<User> {
  return serverFetch<User>('/api/v1/auth/me');
}
