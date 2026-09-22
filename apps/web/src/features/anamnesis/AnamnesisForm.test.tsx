// @vitest-environment jsdom

import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { finalizeAnamnesisMock, updateAnamnesisMock, pushMock, refreshMock } = vi.hoisted(() => ({
  finalizeAnamnesisMock: vi.fn(),
  updateAnamnesisMock: vi.fn(),
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock('@/features/anamnesis/api', () => ({
  finalizeAnamnesis: finalizeAnamnesisMock,
  updateAnamnesis: updateAnamnesisMock,
  saveProfessionalProfile: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

import { ApiError } from '@/lib/api/problem';

import { AnamnesisForm, anamnesisErrorMessage } from './components/AnamnesisForm';
import { completePayload, makeAnamnesis, makeFinal, makeProfile } from './test-fixtures';

function renderForm(overrides: {
  payload?: Record<string, unknown>;
  profile?: ReturnType<typeof makeProfile> | null;
  canFinalize?: boolean;
}) {
  return render(
    <AnamnesisForm
      clinicId="c1"
      patientId="p1"
      anamnesis={makeAnamnesis({ payload: overrides.payload ?? {} })}
      profile={overrides.profile === undefined ? makeProfile() : overrides.profile}
      patientName="Ana Souza"
      canFinalize={overrides.canFinalize ?? true}
    />,
  );
}

beforeEach(() => {
  finalizeAnamnesisMock.mockReset();
  updateAnamnesisMock.mockReset();
  pushMock.mockReset();
  refreshMock.mockReset();
});

afterEach(cleanup);

describe('AnamnesisForm', () => {
  it('renders every catalog section and pre-fills answers', () => {
    renderForm({
      payload: { allergies: { known_allergy: { value: 'YES', details: 'Penicilina' } } },
    });

    expect(screen.getByRole('heading', { name: 'Queixa principal' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Inventário odontológico' })).toBeTruthy();
    const group = screen.getByRole('group', { name: /Possui alergia conhecida/ });
    expect((within(group).getByLabelText('Sim') as HTMLInputElement).checked).toBe(true);
    expect(
      (screen.getByLabelText(/Informe as substâncias e as reações/) as HTMLTextAreaElement).value,
    ).toBe('Penicilina');
  });

  it('saves the draft with the answered payload', async () => {
    updateAnamnesisMock.mockResolvedValue(makeAnamnesis());
    renderForm({});

    const group = screen.getByRole('group', { name: /Possui alergia conhecida/ });
    await userEvent.click(within(group).getByLabelText('Sim'));
    await userEvent.type(
      screen.getByLabelText(/Informe as substâncias e as reações/),
      'Penicilina',
    );
    await userEvent.click(screen.getByRole('button', { name: /Salvar rascunho/ }));

    await waitFor(() => {
      expect(updateAnamnesisMock).toHaveBeenCalledWith('c1', 'p1', 'a1', {
        allergies: {
          known_allergy: { value: 'YES', details: 'Penicilina' },
          emergency_care: null,
        },
      });
    });
    expect(await screen.findByText('Rascunho salvo.')).toBeTruthy();
  });

  it('clears a stored text answer when the field is emptied', async () => {
    updateAnamnesisMock.mockResolvedValue(makeAnamnesis());
    renderForm({
      payload: { chief_complaint: { description: { text: 'Dor antiga' } } },
    });

    const field = screen.getByLabelText(/Descreva a queixa principal/) as HTMLTextAreaElement;
    expect(field.value).toBe('Dor antiga');
    await userEvent.clear(field);
    await userEvent.click(screen.getByRole('button', { name: /Salvar rascunho/ }));

    await waitFor(() => {
      expect(updateAnamnesisMock).toHaveBeenCalledWith('c1', 'p1', 'a1', {
        chief_complaint: { description: null, duration: null, evolution: null },
      });
    });
  });

  it('blocks finalization while there are pending questions', () => {
    renderForm({});

    const button = screen.getByRole('button', { name: /Concluir anamnese/ }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText(/Resolva as pendências/)).toBeTruthy();
  });

  it('confirms and finalizes a complete anamnesis', async () => {
    finalizeAnamnesisMock.mockResolvedValue(makeFinal(1));
    renderForm({ payload: completePayload() });

    const button = screen.getByRole('button', { name: /Concluir anamnese/ }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    await userEvent.click(button);

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/não é assinatura digital/)).toBeTruthy();
    expect(within(dialog).getByText('Dra. Ana Souza')).toBeTruthy();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Concluir anamnese' }));

    await waitFor(() => {
      expect(finalizeAnamnesisMock).toHaveBeenCalledWith('c1', 'p1', 'a1');
    });
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/clinics/c1/patients/p1/anamnesis/final-1');
    });
  });

  it('asks for the professional profile before finalizing', () => {
    renderForm({ payload: completePayload(), profile: null });

    expect(screen.getByLabelText('Nome profissional')).toBeTruthy();
    expect(screen.getByText(/não valida o número em base externa/)).toBeTruthy();
    expect(
      (screen.getByRole('button', { name: /Concluir anamnese/ }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it('hides the conclusion panel from read-only roles', () => {
    renderForm({ payload: completePayload(), canFinalize: false });

    expect(screen.queryByRole('button', { name: /Concluir anamnese/ })).toBeNull();
    expect(screen.queryByText('Perfil profissional')).toBeNull();
  });

  it('shows the permission message when saving fails', async () => {
    updateAnamnesisMock.mockRejectedValue(new ApiError({ status: 403, title: 'Acesso negado' }));
    renderForm({});

    await userEvent.click(screen.getByRole('button', { name: /Salvar rascunho/ }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Você não tem permissão para alterar esta anamnese.',
    );
  });
});

describe('anamnesisErrorMessage', () => {
  it('maps conflicts and invalid payloads', () => {
    expect(anamnesisErrorMessage(new ApiError({ status: 409, title: 'Conflito' }))).toContain(
      'já foi concluída',
    );
    expect(
      anamnesisErrorMessage(new ApiError({ status: 422, title: 'Dados inválidos' })),
    ).toContain('incompletas');
  });
});
