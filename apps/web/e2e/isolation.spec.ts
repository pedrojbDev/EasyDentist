import type { Page } from '@playwright/test';

import { expect, login, test } from './fixtures';
import type { ClinicFixture, Manifest, UserFixture } from './manifest';

async function expectNoAccess(
  page: Page,
  manifest: Manifest,
  restrictedClinic: ClinicFixture,
  restrictedUser: UserFixture,
  protectedClinic: ClinicFixture,
): Promise<void> {
  await login(page, restrictedUser);
  await expect(page.getByText(restrictedClinic.sentinel)).toBeVisible();
  expect(await page.content()).not.toContain(protectedClinic.sentinel);

  const list = await page.request.get('/api/v1/clinics');
  expect(list.status()).toBe(200);
  const listBody = await list.text();
  expect(listBody).toContain(restrictedClinic.sentinel);
  expect(listBody).not.toContain(protectedClinic.sentinel);

  for (const path of [
    `/api/v1/clinics/${protectedClinic.id}`,
    `/api/v1/clinics/${protectedClinic.id}/settings`,
    `/api/v1/clinics/${protectedClinic.id}/memberships`,
  ]) {
    const response = await page.request.get(path);
    expect(response.status(), path).toBe(404);
    expect(await response.text()).not.toContain(protectedClinic.sentinel);
  }

  for (const path of [
    `/clinics/${protectedClinic.id}`,
    `/clinics/${protectedClinic.id}/settings`,
    `/clinics/${protectedClinic.id}/members`,
  ]) {
    const response = await page.goto(path);
    expect(response?.status(), path).toBe(404);
    expect(await response?.text()).not.toContain(protectedClinic.sentinel);
  }
  expect(await page.content()).not.toContain(protectedClinic.sentinel);
}

test.describe('isolamento cross-tenant', () => {
  test('usuário da Clínica A não acessa a Clínica B por rota, API ou SSR', async ({
    page,
    manifest,
  }) => {
    await expectNoAccess(
      page,
      manifest,
      manifest.clinics.a,
      manifest.users['clinic-a'],
      manifest.clinics.b,
    );
  });

  test('usuário da Clínica B não acessa a Clínica A por rota, API ou SSR', async ({
    page,
    manifest,
  }) => {
    await expectNoAccess(
      page,
      manifest,
      manifest.clinics.b,
      manifest.users['clinic-b'],
      manifest.clinics.a,
    );
  });

  test('usuário multi-clínica acessa as duas por API', async ({ page, manifest }) => {
    await login(page, manifest.users.multi);
    const list = await page.request.get('/api/v1/clinics');
    expect(list.status()).toBe(200);
    const body = await list.text();
    expect(body).toContain(manifest.clinics.a.sentinel);
    expect(body).toContain(manifest.clinics.b.sentinel);
    const protectedClinic = await page.request.get(
      `/api/v1/clinics/${manifest.clinics.b.id}/settings`,
    );
    expect(protectedClinic.status()).toBe(200);
  });
});
