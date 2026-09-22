import { existsSync, readFileSync } from 'node:fs';

import { test as base, expect, type BrowserContext, type Page } from '@playwright/test';

import { readManifest, sessionStatePath, type Manifest } from './manifest';

type Credentials = { email: string; password: string };

type StoredSession = { cookies: Parameters<BrowserContext['addCookies']>[0] };

type Fixtures = {
  manifest: Manifest;
  cspGuard: void;
};

export const test = base.extend<Fixtures>({
  manifest: async ({}, provide) => {
    await provide(readManifest());
  },
  cspGuard: [
    async ({ page }, provide) => {
      const violations: string[] = [];
      page.on('console', (message) => {
        if (message.type() === 'error' && message.text().includes('Content Security Policy')) {
          violations.push(message.text());
        }
      });
      await provide();
      expect(violations, `CSP violations: ${violations.join(' | ')}`).toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/**
 * Authenticates the page. Seeded users reuse the session state created once
 * per run by global-setup; dynamically created users (invitees) fall back to
 * the real form, which is also the path asserted by auth.spec.ts.
 */
export async function login(page: Page, user: Credentials): Promise<void> {
  const statePath = sessionStatePath(user.email);
  if (existsSync(statePath)) {
    const state = JSON.parse(readFileSync(statePath, 'utf8')) as StoredSession;
    await page.context().addCookies(state.cookies);
    await page.goto('/clinics');
    await expect(page).toHaveURL(/\/clinics$/);
    return;
  }
  await loginWithForm(page, user);
}

export async function loginWithForm(page: Page, user: Credentials): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('E-mail', { exact: true }).fill(user.email);
  await page.getByLabel('Senha', { exact: true }).fill(user.password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page).toHaveURL(/\/clinics$/);
}

export function pdfFixture(marker: string): Buffer {
  return Buffer.from(
    `%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Marker (${marker}) >>\nendobj\n%%EOF\n`,
    'utf8',
  );
}
