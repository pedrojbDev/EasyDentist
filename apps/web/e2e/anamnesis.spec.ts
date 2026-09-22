import type { Page } from '@playwright/test';

import { expect, login, test } from './fixtures';

const FIRST_TEXT_ANSWER = 'Resposta E2E 1';

/**
 * Fills every catalog question the same way the API helper does: "Não" for
 * closed questions, the first option for single choice and free text for the
 * textual ones. Finalization only unlocks when no question is pending.
 */
async function fillCompleteDraft(page: Page): Promise<void> {
  const fieldsets = page.locator('form fieldset');
  const fieldsetCount = await fieldsets.count();
  for (let index = 0; index < fieldsetCount; index += 1) {
    const fieldset = fieldsets.nth(index);
    const no = fieldset.getByLabel('Não', { exact: true });
    if ((await no.count()) > 0) {
      await no.first().check();
    } else {
      await fieldset.locator('input[type="radio"]').first().check();
    }
  }

  const textareas = page.locator('form textarea[id^="anamnesis-"]:not([id$="-details"])');
  const textareaCount = await textareas.count();
  for (let index = 0; index < textareaCount; index += 1) {
    await textareas.nth(index).fill(`Resposta E2E ${index + 1}`);
  }
}

test.describe('anamnese', () => {
  test('cria rascunho, conclui a versão 1 e inicia uma revisão com as respostas', async ({
    page,
    manifest,
  }) => {
    test.slow();
    await login(page, manifest.users.multi);
    const clinic = manifest.clinics.a;
    const patient = manifest.patients.a;
    const anamnesisPath = `/clinics/${clinic.id}/patients/${patient.id}/anamnesis`;

    await page.goto(anamnesisPath);
    await expect(page.getByRole('heading', { name: 'Anamnese' })).toBeVisible();
    await expect(page.getByText('Nenhum rascunho em andamento')).toBeVisible();

    await page.getByRole('button', { name: 'Iniciar anamnese' }).click();
    await expect(page.getByText('Rascunho', { exact: true })).toBeVisible();
    await fillCompleteDraft(page);
    await page.getByRole('button', { name: 'Salvar rascunho' }).click();
    await expect(page.getByText('Rascunho salvo.')).toBeVisible();
    await page.reload();
    await expect(page.locator('#anamnesis-chief_complaint-description')).toHaveValue(
      FIRST_TEXT_ANSWER,
    );

    await page.getByRole('button', { name: 'Concluir anamnese' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(manifest.professional_profile.professional_name)).toBeVisible();
    await expect(dialog.getByText('CRO')).toBeVisible();
    await dialog.getByRole('button', { name: 'Concluir anamnese' }).click();

    await expect(page).toHaveURL(
      new RegExp(`/clinics/${clinic.id}/patients/${patient.id}/anamnesis/[0-9a-f-]{36}$`),
    );
    await expect(page.getByRole('heading', { name: 'Anamnese — versão 1' })).toBeVisible();
    await expect(page.getByText('Versão 1', { exact: true })).toBeVisible();
    await expect(
      page.getByText(new RegExp(manifest.professional_profile.professional_name)),
    ).toBeVisible();
    await expect(page.getByText(FIRST_TEXT_ANSWER)).toBeVisible();

    await page.getByRole('button', { name: 'Iniciar revisão desta versão' }).click();
    await expect(page).toHaveURL(new RegExp(`${anamnesisPath}$`));
    await expect(page.getByText('Rascunho', { exact: true })).toBeVisible();
    await expect(page.locator('#anamnesis-chief_complaint-description')).toHaveValue(
      FIRST_TEXT_ANSWER,
    );
    // The concluded version stays in the history and remains the current one.
    await expect(page.getByText('Versão 1', { exact: true })).toBeVisible();
    await expect(page.getByText('Vigente')).toBeVisible();
  });

  test('papel administrativo não acessa o conteúdo clínico', async ({ page, manifest }) => {
    await login(page, manifest.users.admin);
    const clinic = manifest.clinics.a;
    const patient = manifest.patients.a;

    await page.goto(`/clinics/${clinic.id}/patients/${patient.id}/anamnesis`);
    await expect(page.getByText('Acesso restrito')).toBeVisible();
    await expect(
      page.getByText('A anamnese é conteúdo clínico e não está disponível para o seu papel'),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'Anamnese' })).toHaveCount(0);

    const response = await page.request.get(
      `/api/v1/clinics/${clinic.id}/patients/${patient.id}/anamneses`,
    );
    expect(response.status()).toBe(403);
  });
});
