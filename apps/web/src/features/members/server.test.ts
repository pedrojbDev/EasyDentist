import { describe, expect, it, vi } from 'vitest';

const { serverFetchMock } = vi.hoisted(() => ({ serverFetchMock: vi.fn() }));

vi.mock('@/lib/api/server-client', () => ({ serverFetch: serverFetchMock }));

import { listMembersOnServer } from './server';

describe('members server api', () => {
  it('lists the memberships through the server client', async () => {
    serverFetchMock.mockResolvedValueOnce([]);

    await expect(listMembersOnServer('c1')).resolves.toEqual([]);
    expect(serverFetchMock).toHaveBeenCalledWith('/api/v1/clinics/c1/memberships');
  });
});
