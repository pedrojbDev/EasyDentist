import { afterEach, describe, expect, it, vi } from 'vitest';

const { cookiesMock } = vi.hoisted(() => ({ cookiesMock: vi.fn() }));

vi.mock('next/headers', () => ({ cookies: cookiesMock }));

import { ApiError } from './problem';
import { serverFetch } from './server-client';

const fetchMock = vi.fn();

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  fetchMock.mockReset();
  cookiesMock.mockReset();
});

describe('serverFetch', () => {
  it('forwards only the Cookie header to the internal base URL with no-store', async () => {
    vi.stubEnv('API_INTERNAL_BASE_URL', 'http://api.internal:8000');
    cookiesMock.mockResolvedValue({
      getAll: () => [
        { name: 'easydent_session', value: 'session-1' },
        { name: 'easydent_csrf', value: 'csrf-1' },
      ],
    });
    fetchMock.mockResolvedValueOnce(Response.json({ id: '1' }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(serverFetch<{ id: string }>('/api/v1/auth/me')).resolves.toEqual({ id: '1' });

    expect(fetchMock).toHaveBeenCalledWith('http://api.internal:8000/api/v1/auth/me', {
      headers: { Cookie: 'easydent_session=session-1; easydent_csrf=csrf-1' },
      cache: 'no-store',
    });
  });

  it('omits the Cookie header when there is no session', async () => {
    cookiesMock.mockResolvedValue({ getAll: () => [] });
    fetchMock.mockResolvedValueOnce(Response.json({ service: 'api', status: 'ok' }));
    vi.stubGlobal('fetch', fetchMock);

    await serverFetch('/api/v1/health');

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({});
  });

  it('throws ApiError on unauthenticated responses', async () => {
    cookiesMock.mockResolvedValue({ getAll: () => [] });
    fetchMock.mockResolvedValueOnce(
      Response.json(
        { type: 'about:blank', title: 'Não autenticado', status: 401, request_id: 'req-2' },
        { status: 401, headers: { 'Content-Type': 'application/problem+json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const error = await serverFetch('/api/v1/auth/me').catch((cause: unknown) => cause);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).title).toBe('Não autenticado');
  });
});
