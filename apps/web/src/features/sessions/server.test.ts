import { describe, expect, it, vi } from 'vitest';

const { serverFetchMock } = vi.hoisted(() => ({ serverFetchMock: vi.fn() }));

vi.mock('@/lib/api/server-client', () => ({ serverFetch: serverFetchMock }));

import { listSessionsOnServer } from './server';

describe('sessions server api', () => {
  it('lists the sessions through the server client', async () => {
    serverFetchMock.mockResolvedValueOnce([]);

    await expect(listSessionsOnServer()).resolves.toEqual([]);
    expect(serverFetchMock).toHaveBeenCalledWith('/api/v1/auth/sessions');
  });
});
