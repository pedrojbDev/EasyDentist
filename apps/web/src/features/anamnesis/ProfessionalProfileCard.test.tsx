// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { saveProfessionalProfileMock } = vi.hoisted(() => ({
  saveProfessionalProfileMock: vi.fn(),
}));

vi.mock('@/features/anamnesis/api', () => ({
  saveProfessionalProfile: saveProfessionalProfileMock,
}));

import { ApiError } from '@/lib/api/problem';

import {
  ProfessionalProfileCard,
  professionalProfileErrorMessage,
} from './components/ProfessionalProfileCard';
import { makeProfile } from './test-fixtures';

beforeEach(() => {
  saveProfessionalProfileMock.mockReset();
});

afterEach(cleanup);

describe('ProfessionalProfileCard', () => {
  it('shows the form and the CRO disclaimer when there is no profile', () => {
    render(<ProfessionalProfileCard profile={null} />);

    expect(screen.getByLabelText('Nome profissional')).toBeTruthy();
    expect(screen.getByText(/não valida o número em base externa/)).toBeTruthy();
  });

  it('saves the profile and reports it to the caller', async () => {
    const saved = makeProfile({
      professional_name: 'Dr. Bruno Lima',
      cro_number: '98765',
      cro_state: 'PE',
    });
    saveProfessionalProfileMock.mockResolvedValue(saved);
    const onSaved = vi.fn();
    render(<ProfessionalProfileCard profile={null} onSaved={onSaved} />);

    await userEvent.type(screen.getByLabelText('Nome profissional'), 'Dr. Bruno Lima');
    await userEvent.type(screen.getByLabelText('Número do CRO'), '98765');
    await userEvent.type(screen.getByLabelText('UF'), 'pe');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar perfil profissional' }));

    await waitFor(() => {
      expect(saveProfessionalProfileMock).toHaveBeenCalledWith({
        professional_name: 'Dr. Bruno Lima',
        cro_number: '98765',
        cro_state: 'PE',
      });
    });
    expect(onSaved).toHaveBeenCalledWith(saved);
    expect(await screen.findByText('Dr. Bruno Lima')).toBeTruthy();
    expect(screen.getByText((_, element) => element?.textContent === '98765/PE')).toBeTruthy();
  });

  it('validates required fields before calling the API', async () => {
    render(<ProfessionalProfileCard profile={null} />);

    await userEvent.type(screen.getByLabelText('Nome profissional'), 'Dra. Ana');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar perfil profissional' }));

    expect(await screen.findByText(/Informe nome profissional/)).toBeTruthy();
    expect(saveProfessionalProfileMock).not.toHaveBeenCalled();
  });

  it('shows a friendly message on invalid server data', async () => {
    saveProfessionalProfileMock.mockRejectedValue(
      new ApiError({ status: 422, title: 'Dados inválidos' }),
    );
    render(<ProfessionalProfileCard profile={null} />);

    await userEvent.type(screen.getByLabelText('Nome profissional'), 'Dra. Ana');
    await userEvent.type(screen.getByLabelText('Número do CRO'), '123');
    await userEvent.type(screen.getByLabelText('UF'), 'BA');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar perfil profissional' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Verifique nome profissional, número do CRO e UF.',
    );
  });

  it('allows editing an existing profile', async () => {
    render(<ProfessionalProfileCard profile={makeProfile()} />);

    expect(screen.getByText((_, element) => element?.textContent === '12345/BA')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Editar perfil profissional' }));
    expect((screen.getByLabelText('Nome profissional') as HTMLInputElement).value).toBe(
      'Dra. Ana Souza',
    );
  });
});

describe('professionalProfileErrorMessage', () => {
  it('maps invalid payloads and expired sessions', () => {
    expect(
      professionalProfileErrorMessage(new ApiError({ status: 422, title: 'Dados inválidos' })),
    ).toContain('Verifique nome profissional');
    expect(
      professionalProfileErrorMessage(new ApiError({ status: 401, title: 'Não autenticado' })),
    ).toContain('Sessão expirada');
  });
});
