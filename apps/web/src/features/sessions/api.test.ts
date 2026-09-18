import { afterEach, describe, expect, it, vi } from 'vitest';

import { listSessions, revokeSession } from './api';

const fetchMock = vi.fn();

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe('sessions api', () => {
  it('lists the sessions of the current user', async () => {
    fetchMock.mockResolvedValueOnce(
      Response.json([
        {
          id: 's1',
          created_at: '2026-09-17T12:00:00Z',
          last_seen_at: '2026-09-17T12:05:00Z',
          expires_at: '2026-10-17T12:00:00Z',
          current: true,
        },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    const sessions = await listSessions();

    expect(sessions[0].current).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/sessions', expect.objectContaining({}));
  });

  it('revokes a session with csrf protection', async () => {
    fetchMock
      .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-1' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await revokeSession('s2');

    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/sessions/s2');
    expect(init.method).toBe('DELETE');
    expect(init.headers).toMatchObject({ 'X-CSRF-Token': 'csrf-1' });
  });
});
