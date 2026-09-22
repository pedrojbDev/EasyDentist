import { expect, login, test } from './fixtures';
import { findToken } from './helpers/mailpit';
import { inviteeEmail } from './manifest';

test.describe('clínicas, settings e equipe', () => {
  test('seletor lista as duas clínicas e alterna entre as rotas', async ({ page, manifest }) => {
    await login(page, manifest.users.multi);
    await expect(page.getByRole('heading', { name: 'Suas clínicas' })).toBeVisible();
    await expect(page.locator('main ul > li')).toHaveCount(2);
    await expect(page.getByText(manifest.clinics.a.sentinel)).toBeVisible();
    await expect(page.getByText(manifest.clinics.b.sentinel)).toBeVisible();
    await expect(page.getByText('Proprietário')).toBeVisible();
    await expect(page.getByText('Dentista')).toBeVisible();

    await page.getByRole('link', { name: new RegExp(manifest.clinics.a.legal_name) }).click();
    await expect(page).toHaveURL(new RegExp(`/clinics/${manifest.clinics.a.id}$`));
    await expect(page.getByRole('heading', { name: manifest.clinics.a.legal_name })).toBeVisible();

    await page.goto('/clinics');
    await page.getByRole('link', { name: new RegExp(manifest.clinics.b.legal_name) }).click();
    await expect(page).toHaveURL(new RegExp(`/clinics/${manifest.clinics.b.id}$`));
    await expect(page.getByRole('heading', { name: manifest.clinics.b.legal_name })).toBeVisible();
  });

  test('settings permite atualização autorizada e confirma o novo valor', async ({
    page,
    manifest,
  }) => {
    await login(page, manifest.users.multi);
    await page.goto(`/clinics/${manifest.clinics.a.id}/settings`);
    await expect(page.getByRole('heading', { name: 'Ajustes da clínica' })).toBeVisible();

    const displayName = page.getByLabel('Nome comercial');
    const updated = `${manifest.clinics.a.display_name} — ajustada`;
    await expect(displayName).toHaveValue(manifest.clinics.a.display_name);
    await displayName.fill(updated);
    await page.getByRole('button', { name: 'Salvar configurações' }).click();
    await expect(page.getByText('Configurações atualizadas.')).toBeVisible();

    await page.reload();
    await expect(page.getByLabel('Nome comercial')).toHaveValue(updated);
  });

  test('settings são somente leitura para quem não gerencia', async ({ page, manifest }) => {
    await login(page, manifest.users['clinic-a']);
    await page.goto(`/clinics/${manifest.clinics.a.id}/settings`);
    await expect(page.getByRole('heading', { name: 'Ajustes da clínica' })).toBeVisible();
    await expect(page.getByText('Nome comercial')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Salvar configurações' })).toHaveCount(0);
  });

  test('convite é aceito pelo link do Mailpit e ativa o vínculo', async ({
    page,
    browser,
    baseURL,
    manifest,
  }) => {
    await login(page, manifest.users.multi);
    await page.goto(`/clinics/${manifest.clinics.a.id}/members`);

    const email = inviteeEmail(manifest, 'convite');
    const password = `Convite-${manifest.run_id}-senha`;
    const invitedAt = new Date();
    await page.getByLabel('E-mail do convidado').fill(email);
    await page.getByRole('button', { name: 'Enviar convite' }).click();
    await expect(page.getByText(`Convite enviado para ${email}`)).toBeVisible();

    const token = await findToken(email, invitedAt);
    const inviteeContext = await browser.newContext({ baseURL });
    const inviteePage = await inviteeContext.newPage();
    await inviteePage.goto(`/accept-invitation#token=${token}`);
    await inviteePage.getByLabel('Senha (opcional)').fill(password);
    await inviteePage.getByLabel('Confirme a senha').fill(password);
    await inviteePage.getByRole('button', { name: 'Ativar convite' }).click();
    await expect(inviteePage.getByText('Convite aceito com sucesso.')).toBeVisible();
    expect(await inviteePage.evaluate(() => window.location.hash)).toBe('');

    await login(inviteePage, { email, password });
    await expect(inviteePage.getByText(manifest.clinics.a.sentinel)).toBeVisible();
    await inviteeContext.close();
  });

  test('equipe altera papel, remove vínculo e relata o último proprietário', async ({
    page,
    browser,
    baseURL,
    manifest,
  }) => {
    await login(page, manifest.users.multi);
    await page.goto(`/clinics/${manifest.clinics.a.id}/members`);

    const email = inviteeEmail(manifest, 'equipe');
    const password = `Equipe-${manifest.run_id}-senha`;
    const invitedAt = new Date();
    await page.getByLabel('E-mail do convidado').fill(email);
    await page.getByRole('button', { name: 'Enviar convite' }).click();
    await expect(page.getByText(`Convite enviado para ${email}`)).toBeVisible();

    const token = await findToken(email, invitedAt);
    const inviteeContext = await browser.newContext({ baseURL });
    const inviteePage = await inviteeContext.newPage();
    await inviteePage.goto(`/accept-invitation#token=${token}`);
    await inviteePage.getByLabel('Senha (opcional)').fill(password);
    await inviteePage.getByLabel('Confirme a senha').fill(password);
    await inviteePage.getByRole('button', { name: 'Ativar convite' }).click();
    await expect(inviteePage.getByText('Convite aceito com sucesso.')).toBeVisible();
    await inviteeContext.close();

    await page.reload();
    await expect(page.getByText(email)).toBeVisible();
    await page.getByLabel(`Novo papel de ${email}`).selectOption('ASSISTANT');
    await page.getByRole('button', { name: `Alterar papel de ${email}` }).click();
    await expect(page.getByText('Papel atualizado.')).toBeVisible();
    const members = (await (
      await page.request.get(`/api/v1/clinics/${manifest.clinics.a.id}/memberships`)
    ).json()) as Array<{ email?: string; role: string }>;
    expect(members.find((member) => member.email === email)?.role).toBe('ASSISTANT');

    page.once('dialog', (dialog) => void dialog.accept());
    await page.getByRole('button', { name: `Remover ${email}` }).click();
    await expect(page.getByText('Vínculo removido.')).toBeVisible();
    await expect(page.getByText(email)).toHaveCount(0);

    page.once('dialog', (dialog) => void dialog.accept());
    await page.getByRole('button', { name: `Remover ${manifest.users.multi.email}` }).click();
    await expect(
      page.getByText('O último proprietário ativo não pode ser removido ou rebaixado.'),
    ).toBeVisible();
  });
});
