import { createHash } from 'node:crypto';

import { expect, login, pdfFixture, test } from './fixtures';

function sha256(value: Buffer): string {
  return createHash('sha256').update(value).digest('hex');
}

test.describe('documentos', () => {
  test('envia, baixa com o mesmo tamanho e SHA-256, arquiva e restaura', async ({
    page,
    manifest,
  }) => {
    await login(page, manifest.users.multi);
    const clinic = manifest.clinics.a;
    const patient = manifest.patients.a;
    const title = `Laudo E2E ${manifest.run_id}`;
    const contents = pdfFixture(`m26-${manifest.run_id}`);

    await page.goto(`/clinics/${clinic.id}/patients/${patient.id}/documents`);
    await expect(page.getByRole('heading', { name: 'Documentos', exact: true })).toBeVisible();
    await expect(page.getByText('Selecionar arquivo')).toBeVisible();
    await expect(page.getByText('Nenhum arquivo selecionado.')).toBeVisible();

    await page.locator('#document-file').setInputFiles({
      name: 'laudo-e2e.pdf',
      mimeType: 'application/pdf',
      buffer: contents,
    });
    await expect(page.getByText(/laudo-e2e\.pdf ·/)).toBeVisible();
    await page.getByLabel('Título').fill(title);
    await page.getByRole('button', { name: 'Enviar documento' }).click();
    await expect(page.getByText('Documento enviado com sucesso.')).toBeVisible();

    const row = page.getByRole('row', { name: new RegExp(title) });
    await expect(row).toBeVisible();
    const href = await row.getByRole('link', { name: `Baixar ${title}` }).getAttribute('href');
    expect(href).toBeTruthy();

    const download = await page.request.get(href as string);
    expect(download.status()).toBe(200);
    const body = await download.body();
    expect(body.length).toBe(contents.length);
    expect(sha256(body)).toBe(sha256(contents));
    expect(download.headers()['content-disposition']).toContain('attachment');
    expect(download.headers()['content-type']).toContain('application/pdf');

    await row.getByRole('button', { name: `Arquivar ${title}` }).click();
    await expect(page.getByText('Documento arquivado.')).toBeVisible();
    await expect(page.getByRole('row', { name: new RegExp(title) })).toHaveCount(0);

    await page.getByLabel('Filtrar por situação').selectOption('ARCHIVED');
    const archivedRow = page.getByRole('row', { name: new RegExp(title) });
    await expect(archivedRow).toBeVisible();
    await archivedRow.getByRole('button', { name: `Restaurar ${title}` }).click();
    await expect(page.getByText('Documento restaurado.')).toBeVisible();
    await expect(page.getByRole('row', { name: new RegExp(title) })).toHaveCount(0);
  });

  test('anônimo não acessa a página, a listagem nem o conteúdo', async ({ page, manifest }) => {
    const clinic = manifest.clinics.a;
    const patient = manifest.patients.a;
    const documentId = crypto.randomUUID();

    await page.goto(`/clinics/${clinic.id}/patients/${patient.id}/documents`);
    await expect(page).toHaveURL(/\/login$/);

    const list = await page.request.get(
      `/api/v1/clinics/${clinic.id}/patients/${patient.id}/documents`,
    );
    expect(list.status()).toBe(401);

    const content = await page.request.get(
      `/api/v1/clinics/${clinic.id}/patients/${patient.id}/documents/${documentId}/content`,
    );
    expect(content.status()).toBe(401);
  });

  test('papel administrativo não envia documento clínico', async ({ page, manifest }) => {
    await login(page, manifest.users.admin);
    const clinic = manifest.clinics.a;
    const patient = manifest.patients.a;

    await page.goto(`/clinics/${clinic.id}/patients/${patient.id}/documents`);
    await expect(page.getByRole('heading', { name: 'Documentos', exact: true })).toBeVisible();
    const category = page.getByLabel('Categoria', { exact: true });
    await expect(category).toBeVisible();
    expect(await category.locator('option').allTextContents()).toEqual(['Administrativo']);

    const csrfResponse = await page.request.get('/api/v1/auth/csrf');
    const { csrf_token } = (await csrfResponse.json()) as { csrf_token: string };
    const denied = await page.request.post(
      `/api/v1/clinics/${clinic.id}/patients/${patient.id}/documents`,
      {
        multipart: {
          title: 'Documento clínico indevido',
          category: 'CLINICAL',
          file: {
            name: 'indevido.pdf',
            mimeType: 'application/pdf',
            buffer: pdfFixture('admin-denied'),
          },
        },
        headers: { 'X-CSRF-Token': csrf_token, Origin: new URL(page.url()).origin },
      },
    );
    expect(denied.status()).toBe(403);
  });

  test('gestão clínica não envia documento administrativo', async ({ page, manifest }) => {
    await login(page, manifest.users['clinic-a']);
    const clinic = manifest.clinics.a;
    const patient = manifest.patients.a;

    await page.goto(`/clinics/${clinic.id}/patients/${patient.id}/documents`);
    const category = page.getByLabel('Categoria', { exact: true });
    await expect(category).toBeVisible();
    expect(await category.locator('option').allTextContents()).toEqual(['Clínico']);

    const csrfResponse = await page.request.get('/api/v1/auth/csrf');
    const { csrf_token } = (await csrfResponse.json()) as { csrf_token: string };
    const denied = await page.request.post(
      `/api/v1/clinics/${clinic.id}/patients/${patient.id}/documents`,
      {
        multipart: {
          title: 'Documento administrativo indevido',
          category: 'ADMINISTRATIVE',
          file: {
            name: 'indevido.pdf',
            mimeType: 'application/pdf',
            buffer: pdfFixture('dentist-denied'),
          },
        },
        headers: { 'X-CSRF-Token': csrf_token, Origin: new URL(page.url()).origin },
      },
    );
    expect(denied.status()).toBe(403);
  });
});
