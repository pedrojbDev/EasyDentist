import { test as base, expect, type Page } from '@playwright/test';

import { readManifest, type Manifest } from './manifest';

type Credentials = { email: string; password: string };

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

export async function login(page: Page, user: Credentials): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('E-mail', { exact: true }).fill(user.email);
  await page.getByLabel('Senha', { exact: true }).fill(user.password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page).toHaveURL(/\/clinics$/);
}
