import { expect, login, test } from './fixtures';

const STATIC_HEADERS = {
  'x-content-type-options': 'nosniff',
  'x-frame-options': 'DENY',
  'referrer-policy': 'strict-origin-when-cross-origin',
  'permissions-policy': 'camera=(), microphone=(), geolocation=()',
  'cross-origin-opener-policy': 'same-origin',
  'cross-origin-resource-policy': 'same-origin',
};

const API_CSP = "default-src 'none'; base-uri 'none'; frame-ancestors 'none'";

function expectWebHeaders(headers: Record<string, string>): void {
  for (const [name, value] of Object.entries(STATIC_HEADERS)) {
    expect(headers[name], name).toBe(value);
  }
  const csp = headers['content-security-policy'];
  expect(csp).toContain("default-src 'self'");
  expect(csp).toMatch(/nonce-[A-Za-z0-9+/=]+/);
  expect(csp).not.toContain("'unsafe-inline'");
  expect(csp).not.toMatch(/https?:/);
  expect(csp).toContain("frame-ancestors 'none'");
  expect(headers['strict-transport-security']).toBeUndefined();
}

test.describe('headers de segurança', () => {
  test('health e páginas públicas carregam os headers com CSP nonce', async ({ request }) => {
    for (const path of ['/health', '/login', '/forgot-password', '/nao-existe']) {
      const response = await request.get(path);
      expectWebHeaders(response.headers());
    }
  });

  test('páginas autenticadas carregam os headers com CSP nonce', async ({ page, manifest }) => {
    await login(page, manifest.users.multi);
    const response = await page.goto('/clinics');

    expect(response).not.toBeNull();
    expectWebHeaders(response?.headers() ?? {});
  });

  test('o rewrite /api/v1 preserva os headers da API', async ({ request }) => {
    const response = await request.get('/api/v1/health');

    expect(response.status()).toBe(200);
    const headers = response.headers();
    expect(headers['content-security-policy']).toBe(API_CSP);
    expect(headers['x-content-type-options']).toBe('nosniff');
    expect(headers['x-frame-options']).toBe('DENY');
  });
});
