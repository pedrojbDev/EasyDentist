import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './problem';

import { apiFetch, apiFetchVoid, apiMutation, csrfHeaders } from './client';

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe('apiFetch', () => {
  it('fetches a relative URL and returns parsed JSON', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: '1' }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiFetch<{ id: string }>('/api/v1/auth/me')).resolves.toEqual({ id: '1' });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/me', expect.objectContaining({}));
  });

  it('sends JSON bodies with the JSON content type', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await apiFetch('/api/v1/auth/login', { method: 'POST', json: { email: 'a@b.c' } });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(init.body).toBe(JSON.stringify({ email: 'a@b.c' }));
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' });
  });

  it('throws ApiError with request_id and retry information', async () => {
    fetchMock.mockResolvedValueOnce(
      Response.json(
        { type: 'about:blank', title: 'Muitas tentativas', status: 429, request_id: 'req-9' },
        {
          status: 429,
          headers: { 'Content-Type': 'application/problem+json', 'Retry-After': '30' },
        },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const error = await apiFetch('/api/v1/auth/login', {
      method: 'POST',
      json: {},
    }).catch((cause: unknown) => cause);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(429);
    expect((error as ApiError).title).toBe('Muitas tentativas');
    expect((error as ApiError).requestId).toBe('req-9');
    expect((error as ApiError).retryAfter).toBe(30);
  });

  it('propagates network failures', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('fetch failed'));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiFetch('/api/v1/auth/me')).rejects.toBeInstanceOf(TypeError);
  });
});

describe('apiFetchVoid', () => {
  it('handles 204 responses without a body', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiFetchVoid('/api/v1/auth/logout')).resolves.toBeUndefined();
  });
});

describe('csrfHeaders', () => {
  it('returns the token issued by the csrf endpoint', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ csrf_token: 'token-value' }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(csrfHeaders()).resolves.toEqual({ 'X-CSRF-Token': 'token-value' });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/csrf', expect.anything());
  });
});

describe('apiMutation', () => {
  it('fetches a csrf token before every mutation and sends it in the header', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 'csrf-1' }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 'csrf-2' }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await apiMutation('PATCH', '/api/v1/clinics/1', { legal_name: 'X' });
    await apiMutation('DELETE', '/api/v1/clinics/1/memberships/2');

    const mutationCalls = fetchMock.mock.calls.filter(([url]) => url !== '/api/v1/auth/csrf') as [
      string,
      RequestInit,
    ][];
    expect(mutationCalls).toHaveLength(2);
    expect(mutationCalls[0][1].headers).toMatchObject({ 'X-CSRF-Token': 'csrf-1' });
    expect(mutationCalls[1][1].headers).toMatchObject({ 'X-CSRF-Token': 'csrf-2' });
    expect(mutationCalls[1][1].method).toBe('DELETE');
  });
});
