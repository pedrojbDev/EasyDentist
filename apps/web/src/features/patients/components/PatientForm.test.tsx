// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { createPatientMock, updatePatientMock, pushMock, refreshMock } = vi.hoisted(() => ({
  createPatientMock: vi.fn(),
  updatePatientMock: vi.fn(),
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock('@/features/patients/api', () => ({
  createPatient: createPatientMock,
  updatePatient: updatePatientMock,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

import { ApiError } from '@/lib/api/problem';

import { PatientForm, patientErrorMessage } from './PatientForm';

const patient = {
  id: 'p1',
  clinic_id: 'c1',
  full_name: 'Ana Souza',
  social_name: null,
  birth_date: '1990-05-06',
  cpf: '52998224725',
  phone: '+5571999112222',
  phone_secondary: null,
  email: 'ana@example.com',
  postal_code: null,
  street: null,
  number: null,
  complement: null,
  district: null,
  city: null,
  state: null,
  occupation: null,
  nationality: null,
  birthplace: null,
  emergency_contact_name: null,
  emergency_contact_relationship: null,
  emergency_contact_phone: null,
  guardian_name: null,
  guardian_relationship: null,
  guardian_phone: null,
  administrative_notes: null,
  status: 'ACTIVE' as const,
  archived_at: null,
  created_at: '2026-09-01T12:00:00Z',
  updated_at: '2026-09-01T12:00:00Z',
};

beforeEach(() => {
  createPatientMock.mockReset();
  updatePatientMock.mockReset();
  pushMock.mockReset();
  refreshMock.mockReset();
});

afterEach(cleanup);

async function fillRequiredFields() {
  await userEvent.type(screen.getByLabelText('Nome completo'), 'Ana Souza');
  fireEvent.change(screen.getByLabelText('Data de nascimento'), {
    target: { value: '1990-05-06' },
  });
  await userEvent.type(screen.getByLabelText('Telefone principal'), '+5571999112222');
}

describe('PatientForm', () => {
  it('blocks creation without the required fields and focuses the first invalid one', async () => {
    render(<PatientForm clinicId="c1" mode="create" />);

    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar paciente' }));

    expect(createPatientMock).not.toHaveBeenCalled();
    expect(screen.getByText('Informe o nome completo.')).toBeTruthy();
    expect(screen.getByText('Informe a data de nascimento.')).toBeTruthy();
    expect(screen.getByText('Informe o telefone principal.')).toBeTruthy();
    const fullName = screen.getByLabelText('Nome completo');
    expect(fullName.getAttribute('aria-invalid')).toBe('true');
    expect(document.activeElement).toBe(fullName);
  });

  it('rejects future birth dates', async () => {
    render(<PatientForm clinicId="c1" mode="create" />);
    await userEvent.type(screen.getByLabelText('Nome completo'), 'Ana Souza');
    fireEvent.change(screen.getByLabelText('Data de nascimento'), {
      target: { value: '2999-01-01' },
    });
    await userEvent.type(screen.getByLabelText('Telefone principal'), '+5571999112222');

    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar paciente' }));

    expect(createPatientMock).not.toHaveBeenCalled();
    expect(screen.getByText('A data de nascimento não pode estar no futuro.')).toBeTruthy();
  });

  it('requires a complete guardian for minors', async () => {
    render(<PatientForm clinicId="c1" mode="create" />);
    await userEvent.type(screen.getByLabelText('Nome completo'), 'Enzo Souza');
    fireEvent.change(screen.getByLabelText('Data de nascimento'), {
      target: { value: '2016-01-10' },
    });
    await userEvent.type(screen.getByLabelText('Telefone principal'), '+5571999112222');
    await userEvent.type(screen.getByLabelText('Nome do responsável'), 'Marta Souza');

    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar paciente' }));

    expect(createPatientMock).not.toHaveBeenCalled();
    expect(
      screen.getByText('Paciente menor de idade exige responsável com nome, vínculo e telefone.'),
    ).toBeTruthy();
  });

  it('requires name and phone when an emergency contact is informed', async () => {
    render(<PatientForm clinicId="c1" mode="create" />);
    await fillRequiredFields();
    await userEvent.type(screen.getByLabelText('Vínculo do contato de emergência'), 'Irmão');

    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar paciente' }));

    expect(createPatientMock).not.toHaveBeenCalled();
    expect(screen.getByText('Contato de emergência exige nome e telefone.')).toBeTruthy();
  });

  it('rejects CPF with a broken checksum', async () => {
    render(<PatientForm clinicId="c1" mode="create" />);
    await fillRequiredFields();
    await userEvent.type(screen.getByLabelText('CPF'), '529.982.247-24');

    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar paciente' }));

    expect(createPatientMock).not.toHaveBeenCalled();
    expect(screen.getByText('Informe um CPF válido.')).toBeTruthy();
  });

  it('creates a patient and navigates to the detail page', async () => {
    createPatientMock.mockResolvedValue({ ...patient, id: 'p9' });
    render(<PatientForm clinicId="c1" mode="create" />);
    await fillRequiredFields();
    await userEvent.type(screen.getByLabelText('CPF'), '529.982.247-25');

    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar paciente' }));

    await waitFor(() => {
      expect(createPatientMock).toHaveBeenCalledWith(
        'c1',
        expect.objectContaining({
          full_name: 'Ana Souza',
          birth_date: '1990-05-06',
          phone: '+5571999112222',
          cpf: '52998224725',
        }),
      );
    });
    expect(pushMock).toHaveBeenCalledWith('/clinics/c1/patients/p9');
  });

  it('edits a patient with prefilled values and confirms the success', async () => {
    updatePatientMock.mockResolvedValue({ ...patient, social_name: 'Ana S.' });
    render(<PatientForm clinicId="c1" mode="edit" patient={patient} />);

    expect((screen.getByLabelText('Nome completo') as HTMLInputElement).value).toBe('Ana Souza');
    expect((screen.getByLabelText('CPF') as HTMLInputElement).value).toBe('529.982.247-25');

    const socialName = screen.getByLabelText('Nome social');
    await userEvent.type(socialName, 'Ana S.');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }));

    await waitFor(() => {
      expect(updatePatientMock).toHaveBeenCalledWith(
        'c1',
        'p1',
        expect.objectContaining({ social_name: 'Ana S.' }),
      );
    });
    expect(refreshMock).toHaveBeenCalled();
    expect((await screen.findByRole('status')).textContent).toContain(
      'Dados do paciente atualizados.',
    );
  });

  it('maps duplicate CPF to a conflict message', async () => {
    createPatientMock.mockRejectedValue(new ApiError({ status: 409, title: 'Conflito' }));
    render(<PatientForm clinicId="c1" mode="create" />);
    await fillRequiredFields();

    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar paciente' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Já existe um paciente com este CPF nesta clínica.',
    );
  });

  it('maps a forbidden response to a permission message', async () => {
    updatePatientMock.mockRejectedValue(new ApiError({ status: 403, title: 'Acesso negado' }));
    render(<PatientForm clinicId="c1" mode="edit" patient={patient} />);

    await userEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Você não tem permissão para alterar este paciente.',
    );
  });
});

describe('patientErrorMessage', () => {
  it('maps conflicts, validation, rate limits and unknown failures', () => {
    expect(patientErrorMessage(new ApiError({ status: 409, title: 'Conflito' }))).toBe(
      'Já existe um paciente com este CPF nesta clínica.',
    );
    expect(patientErrorMessage(new ApiError({ status: 422, title: 'Dados inválidos' }))).toBe(
      'Não foi possível salvar o paciente. Verifique os campos e tente novamente.',
    );
    expect(
      patientErrorMessage(new ApiError({ status: 429, title: 'Muitas tentativas', retryAfter: 4 })),
    ).toBe('Muitas tentativas. Tente novamente em 4 segundos.');
    expect(patientErrorMessage(new TypeError('fetch failed'))).toBe(
      'Não foi possível salvar o paciente. Tente novamente.',
    );
  });
});
