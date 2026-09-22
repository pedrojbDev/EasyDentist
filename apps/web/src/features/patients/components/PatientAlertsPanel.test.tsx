// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { createPatientAlertMock, updatePatientAlertMock } = vi.hoisted(() => ({
  createPatientAlertMock: vi.fn(),
  updatePatientAlertMock: vi.fn(),
}));

vi.mock('@/features/patients/api', () => ({
  createPatientAlert: createPatientAlertMock,
  updatePatientAlert: updatePatientAlertMock,
}));

import { ApiError } from '@/lib/api/problem';

import { alertErrorMessage, PatientAlertsPanel } from './PatientAlertsPanel';

const alerts = [
  {
    id: 'a1',
    clinic_id: 'c1',
    patient_id: 'p1',
    kind: 'ALLERGY' as const,
    description: 'Alergia a dipirona',
    status: 'ACTIVE' as const,
    resolved_at: null,
    created_by_user_id: 'u1',
    created_at: '2026-09-10T12:00:00Z',
    updated_at: '2026-09-10T12:00:00Z',
  },
];

beforeEach(() => {
  createPatientAlertMock.mockReset();
  updatePatientAlertMock.mockReset();
});

afterEach(cleanup);

describe('PatientAlertsPanel', () => {
  it('lists alerts with pt-BR kind and status', () => {
    render(<PatientAlertsPanel clinicId="c1" patientId="p1" alerts={alerts} canManage={true} />);

    expect(screen.getAllByText('Alergia').length).toBeGreaterThan(0);
    expect(screen.getByText('Ativo')).toBeTruthy();
    expect(screen.getByText('Alergia a dipirona')).toBeTruthy();
  });

  it('shows an empty state without alerts', () => {
    render(<PatientAlertsPanel clinicId="c1" patientId="p1" alerts={[]} canManage={true} />);

    expect(screen.getByText('Nenhum alerta clínico registrado.')).toBeTruthy();
  });

  it('hides the form and the actions from read-only roles', () => {
    render(<PatientAlertsPanel clinicId="c1" patientId="p1" alerts={alerts} canManage={false} />);

    expect(screen.queryByLabelText('Descrição do alerta')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Adicionar alerta' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Resolver' })).toBeNull();
  });

  it('registers a new alert and prepends it to the list', async () => {
    createPatientAlertMock.mockResolvedValue({
      ...alerts[0],
      id: 'a2',
      kind: 'CLINICAL_RISK',
      description: 'Risco de sangramento',
    });
    render(<PatientAlertsPanel clinicId="c1" patientId="p1" alerts={alerts} canManage={true} />);

    await userEvent.selectOptions(screen.getByLabelText('Tipo do alerta'), 'CLINICAL_RISK');
    await userEvent.type(screen.getByLabelText('Descrição do alerta'), 'Risco de sangramento');
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar alerta' }));

    await waitFor(() => {
      expect(createPatientAlertMock).toHaveBeenCalledWith('c1', 'p1', {
        kind: 'CLINICAL_RISK',
        description: 'Risco de sangramento',
      });
    });
    expect(await screen.findByText('Risco de sangramento')).toBeTruthy();
    expect(screen.getByText('Alerta registrado.')).toBeTruthy();
    expect((screen.getByLabelText('Descrição do alerta') as HTMLTextAreaElement).value).toBe('');
  });

  it('resolves an alert and updates its badge', async () => {
    updatePatientAlertMock.mockResolvedValue({
      ...alerts[0],
      status: 'RESOLVED',
      resolved_at: '2026-09-22T12:00:00Z',
    });
    render(<PatientAlertsPanel clinicId="c1" patientId="p1" alerts={alerts} canManage={true} />);

    await userEvent.click(screen.getByRole('button', { name: 'Resolver' }));

    await waitFor(() => {
      expect(updatePatientAlertMock).toHaveBeenCalledWith('c1', 'p1', 'a1', {
        status: 'RESOLVED',
      });
    });
    expect(await screen.findByText('Resolvido')).toBeTruthy();
  });

  it('shows the permission message on 403', async () => {
    createPatientAlertMock.mockRejectedValue(new ApiError({ status: 403, title: 'Acesso negado' }));
    render(<PatientAlertsPanel clinicId="c1" patientId="p1" alerts={alerts} canManage={true} />);

    await userEvent.type(screen.getByLabelText('Descrição do alerta'), 'Risco clínico');
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar alerta' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Você não tem permissão para gerenciar alertas clínicos.',
    );
  });
});

describe('alertErrorMessage', () => {
  it('maps missing patients and invalid payloads', () => {
    expect(alertErrorMessage(new ApiError({ status: 404, title: 'Recurso não encontrado' }))).toBe(
      'Paciente não encontrado. Atualize a página.',
    );
    expect(alertErrorMessage(new ApiError({ status: 422, title: 'Dados inválidos' }))).toBe(
      'Não foi possível salvar o alerta. Verifique os campos e tente novamente.',
    );
  });
});
