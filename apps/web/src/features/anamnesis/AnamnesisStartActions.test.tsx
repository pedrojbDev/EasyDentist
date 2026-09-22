// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { createAnamnesisMock, refreshMock, pushMock } = vi.hoisted(() => ({
  createAnamnesisMock: vi.fn(),
  refreshMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock('@/features/anamnesis/api', () => ({
  createAnamnesis: createAnamnesisMock,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: refreshMock, push: pushMock }),
}));

import { AnamnesisRevisionButton, AnamnesisStartActions } from './components/AnamnesisStartActions';
import { makeAnamnesis, makeFinal } from './test-fixtures';

beforeEach(() => {
  createAnamnesisMock.mockReset();
  refreshMock.mockReset();
  pushMock.mockReset();
});

afterEach(cleanup);

describe('AnamnesisStartActions', () => {
  it('starts an empty anamnesis when there is no final version', async () => {
    createAnamnesisMock.mockResolvedValue(makeAnamnesis());
    render(<AnamnesisStartActions clinicId="c1" patientId="p1" latestFinal={null} />);

    await userEvent.click(screen.getByRole('button', { name: 'Iniciar anamnese' }));

    await waitFor(() => {
      expect(createAnamnesisMock).toHaveBeenCalledWith('c1', 'p1', {});
    });
    expect(refreshMock).toHaveBeenCalled();
  });

  it('starts a revision from the latest final version', async () => {
    createAnamnesisMock.mockResolvedValue(makeAnamnesis());
    render(<AnamnesisStartActions clinicId="c1" patientId="p1" latestFinal={makeFinal(2)} />);

    await userEvent.click(screen.getByRole('button', { name: 'Iniciar revisão da versão 2' }));

    await waitFor(() => {
      expect(createAnamnesisMock).toHaveBeenCalledWith('c1', 'p1', {
        base_version_id: 'final-2',
      });
    });
  });

  it('confirms before starting a blank draft over an existing final version', async () => {
    createAnamnesisMock.mockResolvedValue(makeAnamnesis());
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<AnamnesisStartActions clinicId="c1" patientId="p1" latestFinal={makeFinal(1)} />);

    await userEvent.click(screen.getByRole('button', { name: /Iniciar em branco/ }));

    expect(confirm).toHaveBeenCalledWith(
      'Iniciar um rascunho em branco, sem copiar a versão vigente?',
    );
    await waitFor(() => {
      expect(createAnamnesisMock).toHaveBeenCalledWith('c1', 'p1', {});
    });
    confirm.mockRestore();
  });
});

describe('AnamnesisRevisionButton', () => {
  it('creates the revision and opens the editor', async () => {
    createAnamnesisMock.mockResolvedValue(makeAnamnesis({ base_version_id: 'final-1' }));
    render(<AnamnesisRevisionButton clinicId="c1" patientId="p1" baseVersionId="final-1" />);

    await userEvent.click(screen.getByRole('button', { name: 'Iniciar revisão desta versão' }));

    await waitFor(() => {
      expect(createAnamnesisMock).toHaveBeenCalledWith('c1', 'p1', {
        base_version_id: 'final-1',
      });
    });
    expect(pushMock).toHaveBeenCalledWith('/clinics/c1/patients/p1/anamnesis');
  });
});
