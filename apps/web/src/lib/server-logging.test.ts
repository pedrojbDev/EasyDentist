import { afterEach, describe, expect, it, vi } from 'vitest';

import { logServerEvent, normalizeRoute } from './server-logging';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe('normalizeRoute', () => {
  it('replaces UUID path segments with a template placeholder', () => {
    expect(normalizeRoute('/clinics/0f7c1a2b-3d4e-5f60-7a8b-9c0d1e2f3a4b/settings')).toBe(
      '/clinics/{id}/settings',
    );
    expect(normalizeRoute('/sessions')).toBe('/sessions');
  });
});

describe('logServerEvent', () => {
  it('emits one JSON line with service metadata and allowlisted context', () => {
    vi.stubEnv('APP_ENV', 'production');
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);

    logServerEvent('INFO', {
      event: 'http.request',
      request_id: 'req-1',
      method: 'GET',
      route: '/clinics',
    });

    expect(log).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(String(log.mock.calls[0]?.[0])) as Record<string, unknown>;
    expect(payload).toMatchObject({
      service: 'web',
      environment: 'production',
      level: 'INFO',
      event: 'http.request',
      request_id: 'req-1',
      method: 'GET',
      route: '/clinics',
    });
    expect(payload.timestamp).toEqual(expect.any(String));
  });

  it('routes error events to console.error', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);

    logServerEvent('ERROR', { event: 'http.request', error_type: 'TypeError' });

    expect(error).toHaveBeenCalledTimes(1);
    expect(log).not.toHaveBeenCalled();
  });

  it('never accepts free-form fields outside the allowlist', () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);

    logServerEvent('INFO', { event: 'http.request', request_id: 'req-2' });

    const payload = JSON.parse(String(log.mock.calls[0]?.[0])) as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual(
      ['environment', 'event', 'level', 'request_id', 'service', 'timestamp'].sort(),
    );
  });
});
