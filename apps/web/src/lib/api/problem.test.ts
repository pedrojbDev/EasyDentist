import { describe, expect, it } from 'vitest';

import { GENERIC_ERROR_MESSAGE, apiErrorFrom, readJsonBody } from './problem';

describe('apiErrorFrom', () => {
  it('maps a Problem Details body into ApiError', () => {
    const response = new Response(null, {
      status: 409,
      headers: { 'Retry-After': '90' },
    });

    const error = apiErrorFrom(response, {
      type: 'about:blank',
      title: 'Conflito',
      status: 409,
      request_id: 'req-1',
      detail: 'resource already exists',
    });

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe('ApiError');
    expect(error.status).toBe(409);
    expect(error.title).toBe('Conflito');
    expect(error.detail).toBe('resource already exists');
    expect(error.requestId).toBe('req-1');
    expect(error.retryAfter).toBe(90);
  });

  it('falls back to a generic pt-BR message without leaking body shape', () => {
    const response = new Response(null, { status: 500 });

    const error = apiErrorFrom(response, { unexpected: true });

    expect(error.title).toBe(GENERIC_ERROR_MESSAGE);
    expect(error.detail).toBeUndefined();
    expect(error.requestId).toBeUndefined();
    expect(error.retryAfter).toBeUndefined();
  });

  it('ignores non-numeric Retry-After headers', () => {
    const response = new Response(null, { status: 429, headers: { 'Retry-After': 'soon' } });

    expect(apiErrorFrom(response, {}).retryAfter).toBeUndefined();
  });
});

describe('readJsonBody', () => {
  it('returns undefined for 204 and non-JSON payloads', async () => {
    await expect(readJsonBody(new Response(null, { status: 204 }))).resolves.toBeUndefined();
    await expect(
      readJsonBody(new Response('plain', { headers: { 'Content-Type': 'text/plain' } })),
    ).resolves.toBeUndefined();
  });

  it('parses JSON bodies', async () => {
    await expect(readJsonBody(Response.json({ ok: true }))).resolves.toEqual({ ok: true });
  });
});
