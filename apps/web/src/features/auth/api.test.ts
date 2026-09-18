import { afterEach, describe, expect, it, vi } from 'vitest';

const { redirectToLoginMock } = vi.hoisted(() => ({ redirectToLoginMock: vi.fn() }));

vi.mock('@/lib/api/redirect', () => ({ redirectToLogin: redirectToLoginMock }));

import { ApiError } from '@/lib/api/problem';

import {
  acceptInvitation,
  forgotPassword,
  login,
  logout,
  logoutAll,
  resetPassword,
  verifyEmail,
} from './api';

const fetchMock = vi.fn();

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  redirectToLoginMock.mockReset();
});

function okJson(body: unknown): Response {
  return Response.json(body);
}

describe('auth api', () => {
  it('logs in with csrf protection and returns the user', async () => {
    fetchMock.mockResolvedValueOnce(okJson({ csrf_token: 'csrf-1' })).mockResolvedValueOnce(
      okJson({
        user: { id: '1', email: 'owner@example.com', email_verified_at: null, status: 'ACTIVE' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await login('owner@example.com', 'senha-secreta-123');

    expect(response.user.email).toBe('owner@example.com');
    const [csrfUrl] = fetchMock.mock.calls[0] as [string];
    const [loginUrl, loginInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(csrfUrl).toBe('/api/v1/auth/csrf');
    expect(loginUrl).toBe('/api/v1/auth/login');
    expect(loginInit.method).toBe('POST');
    expect(loginInit.body).toBe(
      JSON.stringify({ email: 'owner@example.com', password: 'senha-secreta-123' }),
    );
    expect(loginInit.headers).toMatchObject({ 'X-CSRF-Token': 'csrf-1' });
  });

  it('does not trigger the global redirect on invalid credentials', async () => {
    fetchMock
      .mockResolvedValueOnce(okJson({ csrf_token: 'csrf-1' }))
      .mockResolvedValueOnce(
        Response.json(
          { type: 'about:blank', title: 'Não autenticado', status: 401 },
          { status: 401, headers: { 'Content-Type': 'application/problem+json' } },
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    await expect(login('owner@example.com', 'senha-errada-123')).rejects.toBeInstanceOf(ApiError);

    expect(redirectToLoginMock).not.toHaveBeenCalled();
  });

  it('revokes only the current session on logout', async () => {
    fetchMock
      .mockResolvedValueOnce(okJson({ csrf_token: 'csrf-1' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await logout();

    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/logout');
    expect(init.method).toBe('POST');
  });

  it('revokes every session on logoutAll', async () => {
    fetchMock
      .mockResolvedValueOnce(okJson({ csrf_token: 'csrf-1' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await logoutAll();

    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/logout-all');
    expect(init.method).toBe('POST');
  });

  it('requests a password reset without revealing account existence', async () => {
    fetchMock
      .mockResolvedValueOnce(okJson({ csrf_token: 'csrf-1' }))
      .mockResolvedValueOnce(new Response(null, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    await forgotPassword('owner@example.com');

    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/password/forgot');
    expect(init.body).toBe(JSON.stringify({ email: 'owner@example.com' }));
  });

  it('resets the password with the token in the body', async () => {
    fetchMock
      .mockResolvedValueOnce(okJson({ csrf_token: 'csrf-1' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await resetPassword('token-1', 'senha-nova-123456');

    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/password/reset');
    expect(init.body).toBe(JSON.stringify({ token: 'token-1', password: 'senha-nova-123456' }));
  });

  it('confirms the e-mail with the token in the body', async () => {
    fetchMock
      .mockResolvedValueOnce(okJson({ csrf_token: 'csrf-1' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await verifyEmail('token-2');

    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/email-verification/confirm');
    expect(init.body).toBe(JSON.stringify({ token: 'token-2' }));
  });

  it('accepts an invitation without a password when none is given', async () => {
    fetchMock
      .mockResolvedValueOnce(okJson({ csrf_token: 'csrf-1' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await acceptInvitation('token-3');

    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/invitations/accept');
    expect(init.body).toBe(JSON.stringify({ token: 'token-3' }));
  });

  it('sends the password on acceptance when provided', async () => {
    fetchMock
      .mockResolvedValueOnce(okJson({ csrf_token: 'csrf-1' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await acceptInvitation('token-4', 'senha-nova-123456');

    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(init.body).toBe(JSON.stringify({ token: 'token-4', password: 'senha-nova-123456' }));
  });
});
