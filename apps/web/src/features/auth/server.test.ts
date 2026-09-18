import { describe, expect, it, vi } from 'vitest';

const { serverFetchMock } = vi.hoisted(() => ({ serverFetchMock: vi.fn() }));

vi.mock('@/lib/api/server-client', () => ({ serverFetch: serverFetchMock }));

import { getCurrentUser } from './server';

describe('auth server api', () => {
  it('fetches the current user through the server client', async () => {
    const user = {
      id: '1',
      email: 'owner@example.com',
      email_verified_at: null,
      status: 'ACTIVE',
    };
    serverFetchMock.mockResolvedValueOnce(user);

    await expect(getCurrentUser()).resolves.toEqual(user);
    expect(serverFetchMock).toHaveBeenCalledWith('/api/v1/auth/me');
  });
});
