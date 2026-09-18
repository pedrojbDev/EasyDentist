// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ConfirmButton } from './confirm-button';

const confirmMock = vi.fn();

beforeEach(() => {
  confirmMock.mockReset();
  vi.stubGlobal('confirm', confirmMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ConfirmButton', () => {
  it('runs the action after confirmation', async () => {
    confirmMock.mockReturnValue(true);
    const onConfirm = vi.fn();
    render(
      <ConfirmButton message="Tem certeza?" onConfirm={onConfirm}>
        Remover
      </ConfirmButton>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Remover' }));

    expect(confirmMock).toHaveBeenCalledWith('Tem certeza?');
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('skips the action when the confirmation is dismissed', async () => {
    confirmMock.mockReturnValue(false);
    const onConfirm = vi.fn();
    render(
      <ConfirmButton message="Tem certeza?" onConfirm={onConfirm}>
        Remover
      </ConfirmButton>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Remover' }));

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('renders destructive actions with the destructive button treatment', () => {
    render(
      <ConfirmButton message="Tem certeza?" onConfirm={() => undefined} variant="destructive">
        Remover
      </ConfirmButton>,
    );

    expect(screen.getByRole('button', { name: 'Remover' }).className).toContain('bg-destructive');
  });
});
