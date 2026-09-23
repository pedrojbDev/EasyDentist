import { expect, login, test } from './fixtures';

function addDays(value: string, count: number): string {
  const date = new Date(`${value}T12:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0, 10);
}

test.describe('agenda clínica', () => {
  test('cadastra recurso, configura expediente e conclui uma consulta', async ({
    page,
    manifest,
  }) => {
    await login(page, manifest.users.multi);
    const clinic = manifest.clinics.a;
    const professionalName = `Profissional E2E ${manifest.run_id}`;

    await page.goto(`/clinics/${clinic.id}/agenda/resources`);
    await expect(page.getByRole('heading', { name: 'Profissionais e salas' })).toBeVisible();
    await page.getByLabel('Nome', { exact: true }).fill(professionalName);
    await page.getByRole('button', { name: 'Adicionar profissional' }).click();
    await expect(page.getByText(professionalName, { exact: true })).toBeVisible();

    const professionalCard = page.locator('li').filter({ hasText: professionalName }).first();
    await professionalCard.getByRole('button', { name: 'Configurar expediente semanal' }).click();
    for (let weekday = 0; weekday < 7; weekday += 1) {
      await professionalCard.getByRole('button', { name: 'Adicionar intervalo' }).click();
      await professionalCard.locator('select').nth(weekday).selectOption(String(weekday));
    }
    await professionalCard.getByRole('button', { name: 'Salvar expediente' }).click();
    await expect(professionalCard.getByText('Expediente atualizado.')).toBeVisible();
    await page.getByLabel('Nome da sala').fill(`Cadeira E2E ${manifest.run_id}`);
    await page.getByRole('button', { name: 'Adicionar sala' }).click();
    await expect(page.getByText(`Cadeira E2E ${manifest.run_id}`, { exact: true })).toBeVisible();

    await page.goto(`/clinics/${clinic.id}/agenda`);
    await expect(page.getByRole('heading', { name: 'Agenda clínica' })).toBeVisible();
    const today = await page.getByLabel('Data selecionada').inputValue();
    const appointmentDate = addDays(today, 2);
    await page.getByLabel('Data selecionada').fill(appointmentDate);

    await page.getByRole('button', { name: 'Bloquear horário' }).click();
    await page.getByLabel('Início local da clínica').fill(`${appointmentDate}T09:00`);
    await page.getByLabel('Fim local da clínica').fill(`${appointmentDate}T10:00`);
    await page.getByLabel('Descrição (opcional)').fill(`Manutenção E2E ${manifest.run_id}`);
    await page.getByRole('button', { name: 'Criar bloqueio' }).click();
    const blockCard = page.getByRole('button', {
      name: new RegExp(`Manutenção E2E ${manifest.run_id}`),
    });
    await expect(blockCard).toBeVisible();
    await blockCard.click();
    await page.getByRole('button', { name: 'Cancelar bloqueio' }).click();

    await page.getByRole('button', { name: 'Novo agendamento' }).click();
    await page.getByLabel('Buscar paciente ativo').fill(manifest.patients.a.full_name);
    const patientSelect = page.getByLabel('Paciente', { exact: true });
    await expect(
      patientSelect.locator('option', { hasText: manifest.patients.a.full_name }),
    ).toBeAttached();
    await patientSelect.selectOption(manifest.patients.a.id);
    await page
      .getByLabel('Profissional', { exact: true })
      .selectOption({ label: professionalName });
    await page
      .getByLabel('Sala (opcional)')
      .selectOption({ label: `Cadeira E2E ${manifest.run_id}` });
    await page.getByLabel('Data e hora local da clínica').fill(`${appointmentDate}T10:30`);
    await page.getByRole('button', { name: 'Agendar consulta' }).click();

    const appointmentCard = page.getByRole('button', {
      name: new RegExp(manifest.patients.a.full_name),
    });
    await expect(appointmentCard).toBeVisible();
    await appointmentCard.click();
    await page.getByRole('button', { name: 'Editar ou remarcar' }).click();
    await page.getByLabel('Data e hora local da clínica').fill(`${appointmentDate}T11:30`);
    await page.getByRole('button', { name: 'Salvar alterações' }).click();
    await expect(appointmentCard).toBeVisible();
    await appointmentCard.click();
    await page.getByRole('button', { name: 'Confirmar consulta' }).click();
    await appointmentCard.click();
    await page.getByRole('button', { name: 'Registrar chegada' }).click();
    await appointmentCard.click();
    await page.getByRole('button', { name: 'Iniciar atendimento' }).click();
    await appointmentCard.click();
    await page.getByRole('button', { name: 'Concluir atendimento' }).click();

    await page.goto(`/clinics/${clinic.id}/patients/${manifest.patients.a.id}`);
    await expect(page.getByRole('heading', { name: 'Histórico de consultas' })).toBeVisible();
    await expect(page.getByText('Concluída', { exact: true })).toBeVisible();

    const cancelDate = addDays(today, 3);
    await page.goto(`/clinics/${clinic.id}/agenda`);
    await page.getByLabel('Data selecionada').fill(cancelDate);
    await page.getByRole('button', { name: 'Novo agendamento' }).click();
    await page.getByLabel('Buscar paciente ativo').fill(manifest.patients.b.full_name);
    const cancelPatient = page.getByLabel('Paciente', { exact: true });
    await expect(
      cancelPatient.locator('option', { hasText: manifest.patients.b.full_name }),
    ).toBeAttached();
    await cancelPatient.selectOption(manifest.patients.b.id);
    await page
      .getByLabel('Profissional', { exact: true })
      .selectOption({ label: professionalName });
    await page.getByLabel('Data e hora local da clínica').fill(`${cancelDate}T13:00`);
    await page.getByRole('button', { name: 'Agendar consulta' }).click();
    const cancelledAppointment = page.getByRole('button', {
      name: new RegExp(manifest.patients.b.full_name),
    });
    await expect(cancelledAppointment).toBeVisible();
    await cancelledAppointment.click();
    await page.getByLabel('Motivo do cancelamento').fill('Paciente solicitou cancelamento');
    await page.getByRole('button', { name: 'Cancelar consulta' }).click();

    const noShowDate = addDays(today, -1);
    await page.getByLabel('Data selecionada').fill(noShowDate);
    await page.getByRole('button', { name: 'Novo agendamento' }).click();
    await page.getByLabel('Buscar paciente ativo').fill(manifest.patients.b.full_name);
    const noShowPatient = page.getByLabel('Paciente', { exact: true });
    await expect(
      noShowPatient.locator('option', { hasText: manifest.patients.b.full_name }),
    ).toBeAttached();
    await noShowPatient.selectOption(manifest.patients.b.id);
    await page
      .getByLabel('Profissional', { exact: true })
      .selectOption({ label: professionalName });
    await page.getByLabel('Data e hora local da clínica').fill(`${noShowDate}T09:00`);
    await page.getByRole('button', { name: 'Agendar consulta' }).click();
    const noShowAppointment = page.getByRole('button', {
      name: new RegExp(manifest.patients.b.full_name),
    });
    await expect(noShowAppointment).toBeVisible();
    await noShowAppointment.click();
    await page.getByRole('button', { name: 'Marcar falta' }).click();

    await page.goto(`/clinics/${clinic.id}/patients/${manifest.patients.b.id}`);
    await expect(page.getByText('Cancelada', { exact: true })).toBeVisible();
    await expect(page.getByText('Faltou', { exact: true })).toBeVisible();
  });
});
