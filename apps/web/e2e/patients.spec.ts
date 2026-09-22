import { expect, login, test } from './fixtures';

test.describe('pacientes', () => {
  test('cadastra, edita, arquiva e restaura um paciente', async ({ page, manifest }) => {
    await login(page, manifest.users.multi);
    const clinic = manifest.clinics.a;
    const name = `Paciente E2E ${manifest.run_id}`;
    const editedName = `${name} Editado`;

    await page.goto(`/clinics/${clinic.id}/patients/new`);
    await expect(page.getByRole('heading', { name: 'Novo paciente' })).toBeVisible();
    await page.getByLabel('Nome completo').fill(name);
    await page.getByLabel('Data de nascimento').fill('1990-05-06');
    await page.getByLabel('Telefone principal').fill('+5571999110000');
    await page.getByLabel('CPF').fill('111.444.777-35');
    await page.getByLabel('Observações administrativas').fill('Cadastro criado pelo E2E.');
    await page.getByRole('button', { name: 'Cadastrar paciente' }).click();

    await expect(page).toHaveURL(new RegExp(`/clinics/${clinic.id}/patients/[0-9a-f-]{36}$`));
    await expect(page.getByRole('heading', { name })).toBeVisible();
    await expect(page.getByText('CPF 111.444.777-35')).toBeVisible();
    const detailUrl = page.url();

    await page.getByRole('link', { name: 'Editar' }).click();
    await expect(page.getByRole('heading', { name: `Editar ${name}` })).toBeVisible();
    await page.getByLabel('Nome social').fill(editedName);
    await page.getByRole('button', { name: 'Salvar alterações' }).click();
    await expect(page.getByText('Dados do paciente atualizados.')).toBeVisible();

    await page.reload();
    await expect(page.getByLabel('Nome social')).toHaveValue(editedName);

    await page.goto(detailUrl);
    await expect(page.getByText(`Nome social: ${editedName}`)).toBeVisible();
    page.once('dialog', (dialog) => void dialog.accept());
    await page.getByRole('button', { name: `Arquivar ${name}` }).click();
    await expect(page.getByText('Arquivado', { exact: true })).toBeVisible();

    await page.goto(`/clinics/${clinic.id}/patients`);
    await expect(page.getByRole('link', { name, exact: true })).toHaveCount(0);
    await page.getByRole('link', { name: 'Arquivados' }).click();
    const archivedLink = page.getByRole('link', { name, exact: true });
    await expect(archivedLink).toBeVisible();
    await archivedLink.click();
    await expect(page.getByRole('heading', { name })).toBeVisible();

    page.once('dialog', (dialog) => void dialog.accept());
    await page.getByRole('button', { name: `Restaurar ${name}` }).click();
    await expect(page.getByText('Ativo', { exact: true })).toBeVisible();

    await page.goto(`/clinics/${clinic.id}/patients`);
    await expect(page.getByRole('link', { name, exact: true })).toBeVisible();
  });

  test('papel sem permissão não vê as ações de cadastro e edição', async ({ page, manifest }) => {
    await login(page, manifest.users['clinic-a']);
    const clinic = manifest.clinics.a;

    await page.goto(`/clinics/${clinic.id}/patients`);
    await expect(page.getByRole('heading', { name: 'Pacientes' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Novo paciente' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: manifest.patients.a.full_name })).toBeVisible();

    await page.goto(`/clinics/${clinic.id}/patients/${manifest.patients.a.id}`);
    await expect(page.getByRole('heading', { name: manifest.patients.a.full_name })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Editar' })).toHaveCount(0);
    await expect(
      page.getByRole('button', { name: `Arquivar ${manifest.patients.a.full_name}` }),
    ).toHaveCount(0);
  });

  test('paciente de outra clínica não é acessível por rota ou API', async ({ page, manifest }) => {
    await login(page, manifest.users['clinic-a']);
    const protectedPatient = manifest.patients.b;

    await page.goto(`/clinics/${manifest.clinics.a.id}/patients/${protectedPatient.id}`);
    expect(await page.getByText('Página não encontrada').count()).toBeGreaterThan(0);

    const response = await page.request.get(
      `/api/v1/clinics/${manifest.clinics.a.id}/patients/${protectedPatient.id}`,
    );
    expect(response.status()).toBe(404);
    expect(await response.text()).not.toContain(protectedPatient.sentinel);
  });
});
