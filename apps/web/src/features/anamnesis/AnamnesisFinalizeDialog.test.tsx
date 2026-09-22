// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AnamnesisFinalizeDialog } from './components/AnamnesisFinalizeDialog';
import { makeProfile } from './test-fixtures';

afterEach(cleanup);

describe('AnamnesisFinalizeDialog', () => {
  it('renders nothing when closed', () => {
    render(
      <AnamnesisFinalizeDialog
        open={false}
        patientName="Ana Souza"
        profile={makeProfile()}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        pending={false}
      />,
    );

    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows the snapshot and the not-a-signature notice', () => {
    render(
      <AnamnesisFinalizeDialog
        open={true}
        patientName="Ana Souza"
        profile={makeProfile()}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        pending={false}
      />,
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('Ana Souza');
    expect(dialog.textContent).toContain('Dra. Ana Souza');
    expect(dialog.textContent).toContain('12345/BA');
    expect(dialog.textContent).toContain('não é assinatura digital');
    expect(dialog.textContent).toContain('nova versão imutável');
  });

  it('invokes the confirmation and cancellation callbacks', async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <AnamnesisFinalizeDialog
        open={true}
        patientName="Ana Souza"
        profile={makeProfile()}
        onCancel={onCancel}
        onConfirm={onConfirm}
        pending={false}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Concluir anamnese' }));
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
