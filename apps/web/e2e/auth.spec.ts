import { expect, login, loginWithForm, test } from './fixtures';
import { findToken } from './helpers/mailpit';

test.describe('autenticação', () => {
  test('login válido redireciona para a área autenticada', async ({ page, manifest }) => {
    await login(page, manifest.users.multi);
    await expect(page.getByRole('heading', { name: 'Suas clínicas' })).toBeVisible();
    await expect(page.getByText(manifest.clinics.a.sentinel)).toBeVisible();
    await expect(page.getByText(manifest.clinics.b.sentinel)).toBeVisible();

    const cookies = await page.evaluate(() => document.cookie);
    expect(cookies).not.toContain('easydent_session');
    expect(cookies).toContain('easydent_csrf');
  });

  test('login inválido permanece no formulário com erro genérico', async ({ page, manifest }) => {
    await page.goto('/login');
    await page.getByLabel('E-mail', { exact: true }).fill(manifest.users.multi.email);
    await page.getByLabel('Senha', { exact: true }).fill('senha-invalida-com-12+');
    await page.getByRole('button', { name: 'Entrar' }).click();
    await expect(page.getByText('E-mail ou senha inválidos.')).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test('recuperação redefine a senha pelo token do Mailpit', async ({ page, manifest }) => {
    const requestedAt = new Date();
    await page.goto('/forgot-password');
    await page.getByLabel('E-mail', { exact: true }).fill(manifest.users.recovery.email);
    await page.getByRole('button', { name: 'Enviar instruções' }).click();
    await expect(
      page.getByText('Se existir uma conta com este e-mail, enviaremos as instruções'),
    ).toBeVisible();

    const token = await findToken(manifest.users.recovery.email, requestedAt);
    const newPassword = `Nova-${manifest.run_id}-senha`;

    await page.goto(`/reset-password#token=${token}`);
    await page.getByLabel('Nova senha', { exact: true }).fill(newPassword);
    await page.getByLabel('Confirme a nova senha', { exact: true }).fill(newPassword);
    await page.getByRole('button', { name: 'Redefinir senha' }).click();
    await expect(page.getByText('Senha alterada com sucesso.')).toBeVisible();
    expect(page.url()).not.toContain('token=');
    expect(await page.evaluate(() => window.location.hash)).toBe('');

    await loginWithForm(page, { email: manifest.users.recovery.email, password: newPassword });
  });

  test('verificação de e-mail consome o token e confirma o estado', async ({ page, manifest }) => {
    await login(page, manifest.users.unverified);
    const requestedAt = new Date();

    const csrfResponse = await page.request.get('/api/v1/auth/csrf');
    const { csrf_token } = (await csrfResponse.json()) as { csrf_token: string };
    const resend = await page.request.post('/api/v1/auth/email-verification/resend', {
      headers: { 'X-CSRF-Token': csrf_token, Origin: new URL(page.url()).origin },
    });
    expect(resend.status()).toBe(202);

    const token = await findToken(manifest.users.unverified.email, requestedAt);
    await page.goto(`/verify-email#token=${token}`);
    await expect(page.getByText('E-mail confirmado com sucesso.')).toBeVisible();
    expect(page.url()).not.toContain('token=');
    expect(await page.evaluate(() => window.location.hash)).toBe('');

    const me = await page.request.get('/api/v1/auth/me');
    const user = (await me.json()) as { email_verified_at: string | null };
    expect(user.email_verified_at).not.toBeNull();
  });
});
