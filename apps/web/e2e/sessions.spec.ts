import { expect, login, test } from './fixtures';

test.describe('sessões', () => {
  test('lista dispositivos, revoga sessão remota e encerra a sessão atual', async ({
    page,
    browser,
    baseURL,
    manifest,
  }) => {
    await login(page, manifest.users.multi);
    const remoteContext = await browser.newContext({ baseURL });
    const remotePage = await remoteContext.newPage();
    await login(remotePage, manifest.users.multi);

    await page.goto('/sessions');
    await expect(page.getByText('Dispositivos conectados')).toBeVisible();
    await expect(page.getByText('Esta sessão')).toHaveCount(1);

    page.on('dialog', (dialog) => void dialog.accept());
    const remoteRevoke = page.getByRole('button', { name: /Revogar sessão criada em/ });
    expect(await remoteRevoke.count()).toBeGreaterThan(0);
    while ((await remoteRevoke.count()) > 0) {
      const before = await remoteRevoke.count();
      await remoteRevoke.first().click();
      await expect(page.getByText('Sessão encerrada.')).toBeVisible();
      await expect(remoteRevoke).toHaveCount(before - 1);
    }
    await expect(page.getByText('Outro dispositivo')).toHaveCount(0);

    const remoteMe = await remotePage.request.get('/api/v1/auth/me');
    expect(remoteMe.status()).toBe(401);
    await remoteContext.close();

    await page.getByRole('button', { name: 'Encerrar esta sessão' }).click();
    await expect(page).toHaveURL(/\/login$/);
  });

  test('logout global encerra todas as sessões', async ({ page, manifest }) => {
    await login(page, manifest.users.multi);
    await page.goto('/sessions');
    page.once('dialog', (dialog) => void dialog.accept());
    await page
      .getByRole('banner')
      .getByRole('button', { name: 'Sair de todos os dispositivos' })
      .click();
    await expect(page).toHaveURL(/\/login$/);
  });
});
