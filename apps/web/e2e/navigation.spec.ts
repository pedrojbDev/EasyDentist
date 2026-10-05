import { expect, login, test } from './fixtures';

test('desktop navigation keeps the active clinic and switches explicitly', async ({
  page,
  manifest,
}) => {
  await login(page, manifest.users.multi);
  await page.goto(`/clinics/${manifest.clinics.a.id}/agenda`);
  const navigation = page.getByRole('navigation', { name: 'Navegação principal', exact: true });
  await expect(navigation.getByRole('link', { name: 'Agenda', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await navigation.getByRole('link', { name: 'Pacientes', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/clinics/${manifest.clinics.a.id}/patients$`));
  await expect(navigation.getByRole('link', { name: 'Pacientes', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await page.screenshot({ path: 'artifacts/e2e/navigation-desktop.png', fullPage: true });
  await page.getByRole('link', { name: 'Trocar clínica' }).click();
  await expect(page.getByRole('heading', { name: 'Suas clínicas' })).toBeVisible();
  await page.getByRole('link', { name: new RegExp(manifest.clinics.b.legal_name) }).click();
  await expect(page).toHaveURL(new RegExp(`/clinics/${manifest.clinics.b.id}$`));
});

test('mobile navigation opens, closes after choosing a page and fits the viewport', async ({
  page,
  manifest,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, manifest.users['clinic-a']);
  await expect(page).toHaveURL(new RegExp(`/clinics/${manifest.clinics.a.id}/agenda$`));
  const menu = page.getByRole('button', { name: 'Abrir menu' });
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await menu.click();
  await expect(page.getByRole('button', { name: 'Fechar menu' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  await expect(page.getByRole('link', { name: 'Trocar clínica' })).toHaveCount(0);
  const navigation = page.getByRole('navigation', { name: 'Navegação principal', exact: true });
  await page.screenshot({ path: 'artifacts/e2e/navigation-mobile-menu.png', fullPage: true });
  await navigation.getByRole('link', { name: 'Pacientes', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/clinics/${manifest.clinics.a.id}/patients$`));
  await expect(page.getByRole('button', { name: 'Abrir menu' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  expect(await page.content()).not.toContain(manifest.clinics.b.sentinel);
  await page.screenshot({ path: 'artifacts/e2e/navigation-mobile.png', fullPage: true });
});
