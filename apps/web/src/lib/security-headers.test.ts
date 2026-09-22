import { describe, expect, it } from 'vitest';

import {
  CSP_HEADER_NAME,
  HSTS_VALUE,
  STATIC_SECURITY_HEADERS,
  buildContentSecurityPolicy,
  buildSecurityHeaders,
  generateNonce,
} from './security-headers';

const BASE64_PATTERN = /^[A-Za-z0-9+/]+={0,2}$/;

describe('generateNonce', () => {
  it('produces base64 nonces', () => {
    const nonce = generateNonce();
    expect(nonce).toMatch(BASE64_PATTERN);
    expect(nonce.length).toBeGreaterThanOrEqual(20);
  });

  it('produces a fresh nonce per response', () => {
    expect(generateNonce()).not.toBe(generateNonce());
  });
});

describe('buildContentSecurityPolicy', () => {
  const csp = buildContentSecurityPolicy('abc123');

  it('binds scripts and styles to the response nonce', () => {
    expect(csp).toContain("script-src 'self' 'nonce-abc123' 'strict-dynamic'");
    expect(csp).toContain("style-src 'self' 'nonce-abc123'");
  });

  it('never allows unsafe-inline scripts', () => {
    const scriptDirective = csp.split('; ').find((directive) => directive.startsWith('script-src'));
    expect(scriptDirective).toBeDefined();
    expect(scriptDirective).not.toContain("'unsafe-inline'");
    expect(scriptDirective).not.toContain("'unsafe-eval'");
  });

  it('blocks external origins, objects, framing and external forms', () => {
    expect(csp).not.toMatch(/https?:/);
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("form-action 'self'");
    expect(csp).toContain("base-uri 'self'");
  });

  it('limits images to same-origin and data icons', () => {
    expect(csp).toContain("img-src 'self' data:");
    expect(csp).toContain("connect-src 'self'");
  });
});

describe('buildSecurityHeaders', () => {
  it('always emits the static hardening headers and the CSP', () => {
    const headers = buildSecurityHeaders('nonce-value', { production: false });
    expect(headers).toMatchObject(STATIC_SECURITY_HEADERS);
    expect(headers[CSP_HEADER_NAME]).toContain('nonce-nonce-value');
    expect(headers).not.toHaveProperty('Strict-Transport-Security');
  });

  it('emits HSTS only in production', () => {
    const headers = buildSecurityHeaders('nonce-value', { production: true });
    expect(headers['Strict-Transport-Security']).toBe(HSTS_VALUE);
  });
});
